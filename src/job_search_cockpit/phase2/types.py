from dataclasses import dataclass
from enum import StrEnum


class Phase2Action(StrEnum):
    ACTIVATION_VIEW = "activation_view"
    PROVIDER = "provider"
    MANUAL_URL = "manual_url"
    DISCOVERY = "discovery"
    SCORING = "scoring"
    PUBLICATION = "publication"
    HANDOFF = "handoff"


class Phase2ActivationUnavailable(RuntimeError):
    """Raised when Phase II cannot safely perform the requested action."""


@dataclass(frozen=True, slots=True)
class ActivationCommand:
    actor: str
    confirmation: str
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Phase2ActivationView:
    state: str
    reason: str
    activation_generation: int
    revocation_generation: int
    restore_generation: int
    receipt_id: str | None
    active_profile_version: int | None
