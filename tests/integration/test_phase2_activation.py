from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from job_search_cockpit.phase1_contract.service import Phase1ContractUnavailable
from job_search_cockpit.phase1_contract.snapshots import (
    Phase1AcceptanceReceiptSnapshot,
    Phase1ActivationInputs,
    Phase1ReadinessSnapshot,
    SearchProfileSnapshot,
)
from job_search_cockpit.phase2.activation import Phase2ActivationService
from job_search_cockpit.phase2.config import Phase2Settings
from job_search_cockpit.phase2.database import create_phase2_engine, upgrade_phase2_database
from job_search_cockpit.phase2.mutation import Phase2InstanceLock, Phase2MutationCoordinator
from job_search_cockpit.phase2.types import (
    ActivationCommand,
    Phase2Action,
    Phase2ActivationUnavailable,
)
from job_search_cockpit.search_profile.catalog import build_profile_v1


class FixturePhase1Port:
    def __init__(self) -> None:
        profile = SearchProfileSnapshot(
            version_number=1,
            payload=build_profile_v1(),
            active_profile_generation=1,
            fingerprint="p" * 64,
        )
        self.current = Phase1ActivationInputs(
            acceptance_receipt=Phase1AcceptanceReceiptSnapshot(
                id="receipt-1",
                application_build="test-build",
                schema_revision="0002_phase1_contract",
                acceptance_suite_version="phase1-acceptance-test-v1",
                acceptance_run_id="run-1",
                result_fingerprint="r" * 64,
                restore_high_water_mark=0,
                accepted_at="2026-08-24T00:00:00+00:00",
                fingerprint="a" * 64,
            ),
            readiness=Phase1ReadinessSnapshot(
                ready_for_phase_2=True,
                manifest_version="four-source-v1",
                import_run_id="import-1",
                source_hashes={"assessment": "s" * 64},
                active_profile_version=1,
                readiness_generation=1,
                authority_high_water_mark=1,
                restore_generation=0,
                fingerprint="d" * 64,
            ),
            profile=profile,
        )

    def activation_inputs(self) -> Phase1ActivationInputs:
        return self.current

    def revalidate_activation_inputs(
        self, expected: Phase1ActivationInputs
    ) -> Phase1ActivationInputs:
        if self.current != expected:
            raise Phase1ContractUnavailable("The Phase I profile generation changed.")
        return self.current


@contextmanager
def _service(
    settings: Phase2Settings,
) -> Iterator[tuple[Phase2ActivationService, FixturePhase1Port]]:
    upgrade_phase2_database(f"sqlite:///{settings.database_path}")
    engine = create_phase2_engine(settings)
    lock = Phase2InstanceLock.acquire(settings)
    coordinator = Phase2MutationCoordinator(settings, engine, lock)
    port = FixturePhase1Port()
    try:
        yield Phase2ActivationService(port, coordinator), port
    finally:
        coordinator.dispose()
        lock.release()


def test_activation_requires_exact_user_confirmation(phase2_settings: Phase2Settings) -> None:
    with (
        _service(phase2_settings) as (service, _port),
        pytest.raises(Phase2ActivationUnavailable, match="confirmation"),
    ):
        service.activate(ActivationCommand(actor="Varun", confirmation="proceed"))


def test_activation_suspends_when_phase1_inputs_change(phase2_settings: Phase2Settings) -> None:
    with _service(phase2_settings) as (service, port):
        grant = service.activate(ActivationCommand(actor="Varun", confirmation="ENABLE PHASE II"))
        assert grant.state == "active"

        port.current = port.current.model_copy(
            update={
                "profile": port.current.profile.model_copy(
                    update={"active_profile_generation": 2}
                )
            }
        )
        assert service.validate_current().state == "suspended"


def test_all_future_live_actions_remain_denied(phase2_settings: Phase2Settings) -> None:
    with _service(phase2_settings) as (service, _port):
        service.activate(ActivationCommand(actor="Varun", confirmation="ENABLE PHASE II"))

        with pytest.raises(Phase2ActivationUnavailable, match="not implemented"):
            service.revalidate_before(Phase2Action.SCORING)
