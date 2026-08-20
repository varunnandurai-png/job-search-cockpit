from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal


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
