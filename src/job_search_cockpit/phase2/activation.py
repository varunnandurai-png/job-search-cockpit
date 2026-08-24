from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.orm import Session

from job_search_cockpit.phase1_contract.service import Phase1ContractUnavailable
from job_search_cockpit.phase1_contract.snapshots import (
    Phase1ActivationInputs,
    canonical_fingerprint,
)
from job_search_cockpit.phase2.models import Phase2ActivationGrant, Phase2AuthorityState
from job_search_cockpit.phase2.mutation import Phase2MutationCoordinator
from job_search_cockpit.phase2.recovery_ledger import RecoveryEvent
from job_search_cockpit.phase2.types import (
    ActivationCommand,
    Phase2Action,
    Phase2ActivationUnavailable,
    Phase2ActivationView,
)
from job_search_cockpit.ports import Phase1MatchingPort


class Phase2ActivationService:
    def __init__(
        self, phase1_port: Phase1MatchingPort, coordinator: Phase2MutationCoordinator
    ) -> None:
        self.phase1_port = phase1_port
        self._coordinator = coordinator

    @staticmethod
    def _view(
        state: Phase2AuthorityState, grant: Phase2ActivationGrant | None
    ) -> Phase2ActivationView:
        snapshot = grant.snapshot_json if grant is not None else {}
        receipt = snapshot.get("acceptance_receipt", {}) if isinstance(snapshot, dict) else {}
        profile = snapshot.get("profile", {}) if isinstance(snapshot, dict) else {}
        return Phase2ActivationView(
            state=grant.state if grant is not None else "inactive",
            reason=grant.confirmation if grant is not None and grant.state != "active" else "",
            activation_generation=state.activation_generation,
            revocation_generation=state.revocation_generation,
            restore_generation=state.restore_generation,
            receipt_id=(
                str(receipt["id"])
                if isinstance(receipt, dict) and receipt.get("id") is not None
                else None
            ),
            active_profile_version=(
                int(profile["version_number"])
                if isinstance(profile, dict) and profile.get("version_number") is not None
                else None
            ),
        )

    @staticmethod
    def _current(session: Session) -> tuple[Phase2AuthorityState, Phase2ActivationGrant | None]:
        state = session.get(Phase2AuthorityState, 1)
        if state is None:
            raise Phase2ActivationUnavailable("The Phase II authority state is unavailable.")
        grant = (
            session.get(Phase2ActivationGrant, state.current_grant_id)
            if state.current_grant_id is not None
            else None
        )
        return state, grant

    def activation_view(self) -> Phase2ActivationView:
        with self._coordinator._session_factory() as session:
            state, grant = self._current(session)
            return self._view(state, grant)

    def activation_blocker(self) -> str | None:
        view = self.activation_view()
        if view.state == "active":
            return None
        if view.state == "suspended":
            return view.reason or "Phase II is suspended and must be confirmed again."
        try:
            self.phase1_port.activation_inputs()
        except (Phase1ContractUnavailable, ValueError):
            return "Record the verified Phase I acceptance receipt before enabling Phase II."
        return None

    def activate(self, command: ActivationCommand) -> Phase2ActivationView:
        if command.confirmation != "ENABLE PHASE II":
            raise Phase2ActivationUnavailable("Type the exact activation confirmation.")
        if not command.actor.strip():
            raise Phase2ActivationUnavailable("An activation actor is required.")
        try:
            inputs = self.phase1_port.activation_inputs()
        except (Phase1ContractUnavailable, ValueError) as error:
            raise Phase2ActivationUnavailable(str(error)) from error

        def issue(session: Session) -> Phase2ActivationView:
            state, current = self._current(session)
            if current is not None and current.state == "active":
                raise Phase2ActivationUnavailable("Phase II is already active.")
            state.activation_generation += 1
            snapshot_json = inputs.model_dump(mode="json")
            grant = Phase2ActivationGrant(
                id=str(uuid4()),
                state="active",
                snapshot_json=snapshot_json,
                snapshot_fingerprint=canonical_fingerprint(snapshot_json),
                confirmation=command.confirmation,
                actor=command.actor.strip(),
                expected_activation_generation=state.activation_generation,
                supersedes_grant_id=current.id if current is not None else None,
            )
            session.add(grant)
            state.current_grant_id = grant.id
            session.flush()
            return self._view(state, grant)

        view = self._coordinator.run(issue, "issue_phase2_activation", actor=command.actor)
        self._coordinator.recovery_ledger.append(
            RecoveryEvent(
                event_id=str(uuid4()),
                event_type="activation_issued",
                payload={
                    "activation_generation": view.activation_generation,
                    "actor": command.actor,
                },
                created_at=datetime.now(UTC),
            )
        )
        return view

    def suspend(
        self, reason: str, *, prior_grant: Phase2ActivationGrant | None = None
    ) -> Phase2ActivationView:
        def record(session: Session) -> Phase2ActivationView:
            state, current = self._current(session)
            source = current or prior_grant
            if source is None:
                return self._view(state, None)
            state.revocation_generation += 1
            grant = Phase2ActivationGrant(
                id=str(uuid4()),
                state="suspended",
                snapshot_json=source.snapshot_json,
                snapshot_fingerprint=source.snapshot_fingerprint,
                confirmation=reason,
                actor="system",
                expected_activation_generation=state.activation_generation,
                supersedes_grant_id=source.id,
            )
            session.add(grant)
            state.current_grant_id = grant.id
            session.flush()
            return self._view(state, grant)

        view = self._coordinator.run(record, "suspend_phase2_activation")
        if view.state == "suspended":
            self._coordinator.recovery_ledger.append(
                RecoveryEvent(
                    event_id=str(uuid4()),
                    event_type="activation_suspended",
                    payload={"reason": reason, "revocation_generation": view.revocation_generation},
                    created_at=datetime.now(UTC),
                )
            )
        return view

    def validate_current(self) -> Phase2ActivationView:
        with self._coordinator._session_factory() as session:
            state, grant = self._current(session)
            if grant is None or grant.state != "active":
                return self._view(state, grant)
        try:
            expected = Phase1ActivationInputs.model_validate(grant.snapshot_json)
            self.phase1_port.revalidate_activation_inputs(expected)
        except (Phase1ContractUnavailable, ValidationError, ValueError) as error:
            return self.suspend(f"Phase I changed: {error}", prior_grant=grant)
        return self.activation_view()

    def revalidate_before(self, action: Phase2Action) -> Phase2ActivationView:
        view = self.validate_current()
        if action != Phase2Action.ACTIVATION_VIEW:
            raise Phase2ActivationUnavailable("This Phase II action is not implemented.")
        return view

    def restore(self, backup_id: str, actor: str, reason: str) -> Phase2ActivationView:
        with self._coordinator._session_factory() as session:
            _state, prior = self._current(session)
        self._coordinator.restore(backup_id, actor, reason)
        return self.suspend(
            "Phase II data was restored; activation must be confirmed again.",
            prior_grant=prior,
        )
