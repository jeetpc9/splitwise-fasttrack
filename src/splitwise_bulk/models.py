from dataclasses import dataclass
from enum import Enum


class RowStatus(str, Enum):
    SUCCESS = "success"
    DRY_RUN = "dry_run"
    SKIPPED = "skipped"
    ERROR = "error"


class SplitMode(str, Enum):
    HALF = "half"
    WIFE_OWES_FULL = "wife_owes_full"
    SKIP = "skip"

    @classmethod
    def from_text(cls, raw: str, default: "SplitMode") -> "SplitMode":
        value = raw.strip().lower().replace(" ", "_").replace("-", "_")
        if not value:
            return default
        if value in {"split_half", "half", "50", "50/50", "split", "equal", "shared", "h"}:
            return cls.HALF
        if value in {
            "full_other",
            "full",
            "other",
            "partner",
            "wife",
            "100",
            "owes",
            "f",
            "w",
        }:
            return cls.WIFE_OWES_FULL
        if value in {"skip", "no", "ignore", "n", "-", "x"}:
            return cls.SKIP
        raise ValueError(
            f"Unknown split value {raw!r}. Use split_half or full_other."
        )

    def label_for(self, other_name: str = "Other") -> str:
        if self is SplitMode.HALF:
            return "Split half"
        if self is SplitMode.WIFE_OWES_FULL:
            first = other_name.split()[0] if other_name.strip() else "Other"
            return f"Full — {first} owes"
        return "Skip"

    @property
    def label(self) -> str:
        return self.label_for()


@dataclass
class GroupContext:
    group_id: int
    current_user_id: int
    partner_user_id: int
    partner_name: str


@dataclass
class Transaction:
    row_num: int
    description: str
    cost: str
    date: str | None = None
    currency: str = "INR"
    notes: str | None = None
    group_id: int | None = None
    split_mode: SplitMode = SplitMode.HALF
    ingest_key: str | None = None


@dataclass
class ImportResult:
    row: int
    description: str
    cost: str
    date: str
    status: RowStatus
    message: str
    split_mode: str = ""

    def as_dict(self) -> dict:
        return {
            "row": self.row,
            "description": self.description,
            "cost": self.cost,
            "date": self.date,
            "split_mode": self.split_mode,
            "status": self.status.value,
            "message": self.message,
        }
