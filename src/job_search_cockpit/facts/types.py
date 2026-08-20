from enum import StrEnum


class RiskFlag(StrEnum):
    CONFLICT = "conflict"
    QUANTIFIED = "quantified"
    DATE = "date"
    TITLE = "title"
    TEAM_SCOPE = "team_scope"
    POTENTIALLY_CONFIDENTIAL = "potentially_confidential"


class Sensitivity(StrEnum):
    UNREVIEWED = "unreviewed"
    NORMAL = "normal"
    CONFIDENTIAL = "confidential"
