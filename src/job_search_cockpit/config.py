from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from os import environ
from pathlib import Path
from typing import Literal

_GOOGLE_CLIENT_ID_ENV = "JOB_SEARCH_COCKPIT_GOOGLE_OAUTH_CLIENT_ID"
_GOOGLE_CLIENT_SECRET_ENV = "JOB_SEARCH_COCKPIT_GOOGLE_OAUTH_CLIENT_SECRET"


class SourceKind(StrEnum):
    ASSESSMENT = "assessment_markdown"
    PROFILE_JSON = "profile_json"
    MASTER_PROFILE = "master_profile_markdown"
    RESUME_WORKFLOW = "resume_workflow_markdown"


@dataclass(frozen=True, slots=True)
class SourceSpec:
    key: str
    kind: SourceKind
    path: Path
    read_only: bool = True


@dataclass(frozen=True, slots=True)
class Settings:
    host: Literal["127.0.0.1"] = "127.0.0.1"
    data_dir: Path = Path.home() / "Library/Application Support/JobSearchCockpit"
    _source_root: Path = Path("/Users/nandurivarun/Desktop/Documents/CV")
    google_oauth_client_id: str = ""

    @property
    def source_root(self) -> Path:
        return self._source_root

    @property
    def database_path(self) -> Path:
        return self.data_dir / "vault.sqlite3"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def sources(self) -> Sequence[SourceSpec]:
        profile_bank = self.source_root / "Old Data/profile_bank"
        return (
            SourceSpec(
                "assessment",
                SourceKind.ASSESSMENT,
                self.source_root / "Context/job-search-profile-assessment.md",
            ),
            SourceSpec("profile_json", SourceKind.PROFILE_JSON, profile_bank / "profile.json"),
            SourceSpec(
                "master_profile",
                SourceKind.MASTER_PROFILE,
                profile_bank / "Varun_Nanduri_Master_Profile.md",
            ),
            SourceSpec(
                "resume_workflow",
                SourceKind.RESUME_WORKFLOW,
                profile_bank / "Varun_Nanduri_Resume_Workflow.md",
            ),
        )

    @classmethod
    def for_tests(cls, data_dir: Path, source_root: Path) -> "Settings":
        return cls(data_dir=data_dir, _source_root=source_root)

    @classmethod
    def from_environment(cls, *, data_dir: Path | None = None) -> "Settings":
        dotenv_values = _local_dotenv_values()
        if environ.get(_GOOGLE_CLIENT_SECRET_ENV) or dotenv_values.get(_GOOGLE_CLIENT_SECRET_ENV):
            raise ValueError("Google OAuth client secrets are not supported.")
        client_id = environ.get(_GOOGLE_CLIENT_ID_ENV, dotenv_values.get(_GOOGLE_CLIENT_ID_ENV, ""))
        if client_id and (
            len(client_id) > 255
            or client_id != client_id.strip()
            or any(character.isspace() or ord(character) < 32 for character in client_id)
            or not client_id.endswith(".apps.googleusercontent.com")
        ):
            raise ValueError("The Google OAuth client ID is invalid.")
        return cls(data_dir=data_dir or cls().data_dir, google_oauth_client_id=client_id)


def _local_dotenv_values() -> dict[str, str]:
    """Read only the two supported OAuth settings from a regular local .env file."""
    dotenv_path = Path.cwd() / ".env"
    if not dotenv_path.exists():
        return {}
    if dotenv_path.is_symlink() or not dotenv_path.is_file() or dotenv_path.stat().st_size > 8192:
        raise ValueError("The local Google OAuth configuration is invalid.")
    values: dict[str, str] = {}
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in {_GOOGLE_CLIENT_ID_ENV, _GOOGLE_CLIENT_SECRET_ENV}:
            continue
        if key in values:
            raise ValueError("The local Google OAuth configuration is invalid.")
        values[key] = value
    return values
