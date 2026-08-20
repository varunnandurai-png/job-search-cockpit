import json
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from job_search_cockpit.search_profile.catalog import SearchProfilePayload, build_profile_v1
from job_search_cockpit.storage.models import AuditEvent, SearchProfileVersion
from job_search_cockpit.storage.mutation import MutationCoordinator


class ProfileConfirmationError(ValueError):
    """Raised when a locked-profile change lacks exact confirmation."""


class ProfileVersionConflict(RuntimeError):
    """Raised when a profile form was based on an older active version."""


def profile_diff_digest(old: SearchProfilePayload, new: SearchProfilePayload) -> str:
    payload = {
        "old": old.model_dump(mode="json"),
        "new": new.model_dump(mode="json"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(canonical).hexdigest()


def get_active_profile(session: Session) -> SearchProfileVersion:
    try:
        return session.scalars(
            select(SearchProfileVersion).where(SearchProfileVersion.active.is_(True))
        ).one()
    except NoResultFound as error:
        raise ProfileVersionConflict("No active target profile exists.") from error


def seed_profile_v1(coordinator: MutationCoordinator) -> SearchProfileVersion:
    def seed(session: Session) -> SearchProfileVersion:
        existing = session.scalar(
            select(SearchProfileVersion).where(SearchProfileVersion.version_number == 1)
        )
        if existing is not None:
            return existing
        profile = build_profile_v1()
        payload = profile.model_dump(mode="json")
        digest = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        version = SearchProfileVersion(
            id=str(uuid4()),
            version_number=1,
            payload_json=payload,
            active=True,
            reason="Approved Phase 1 search profile",
            confirmation="Approved by authoritative Phase 1 design",
            diff_digest=digest,
        )
        session.add(version)
        session.add(
            AuditEvent(
                id=str(uuid4()),
                event_type="search_profile_seeded",
                area="search_profile",
                subject_id=version.id,
                summary="Target job profile version 1 was created.",
                after_json={"version_number": 1, "diff_digest": digest},
                reason=version.reason,
            )
        )
        return version

    return coordinator.run(seed, "seed_search_profile_v1", expected_version=None)


def confirm_profile_change(
    coordinator: MutationCoordinator,
    payload: SearchProfilePayload,
    reason: str,
    confirmation: str,
    expected_active_version: int,
    expected_diff_digest: str,
) -> SearchProfileVersion:
    if confirmation != "CREATE NEW SEARCH PROFILE VERSION":
        raise ProfileConfirmationError("Type the exact confirmation phrase to create a version.")
    if not reason.strip():
        raise ProfileConfirmationError("A reason is required to create a profile version.")

    def create_version(session: Session) -> SearchProfileVersion:
        active = get_active_profile(session)
        if active.version_number != expected_active_version:
            raise ProfileVersionConflict(
                "The active target profile changed. Review it and try again."
            )
        old = SearchProfilePayload.model_validate(active.payload_json)
        actual_digest = profile_diff_digest(old, payload)
        if actual_digest != expected_diff_digest:
            raise ProfileVersionConflict(
                "The profile changes no longer match the reviewed preview."
            )
        active.active = False
        version = SearchProfileVersion(
            id=str(uuid4()),
            version_number=active.version_number + 1,
            payload_json=payload.model_dump(mode="json"),
            active=True,
            reason=reason.strip(),
            confirmation=confirmation,
            diff_digest=actual_digest,
        )
        session.add(version)
        session.add(
            AuditEvent(
                id=str(uuid4()),
                event_type="search_profile_version_created",
                area="search_profile",
                subject_id=version.id,
                summary=f"Target job profile version {version.version_number} was created.",
                before_json={"version_number": active.version_number},
                after_json={
                    "version_number": version.version_number,
                    "diff_digest": actual_digest,
                },
                reason=reason.strip(),
            )
        )
        return version

    return coordinator.run(
        create_version,
        "change_search_profile",
        expected_version=expected_active_version,
    )
