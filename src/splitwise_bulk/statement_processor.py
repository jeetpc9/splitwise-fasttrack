from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from splitwise_bulk.csv_parser import auto_detect_mapping, load_csv, parse_date, parse_transactions
from splitwise_bulk.models import SplitMode, Transaction

# Descriptions matching these (plus partner name) → partner owes full amount.
TRANSFER_HINTS = (
    "zelle",
    "venmo",
    "paypal",
    "cash app",
    "transfer to",
    "payment to",
    "ach credit",
    "ach debit",
    "wire to",
    "sent to",
    "money sent",
)


@dataclass
class StatementFile:
    path: Path
    headers: list[str]
    rows: list[dict[str, str]]
    mapping: dict[str, str | None] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.path.name


def load_statement_file(path: Path) -> StatementFile:
    headers, rows = load_csv(path)
    mapping = auto_detect_mapping(headers)
    if not mapping.get("cost") and not mapping.get("debit"):
        raise ValueError(f"{path.name}: could not find an amount column.")
    return StatementFile(path=path, headers=headers, rows=rows, mapping=mapping)


def month_key_from_iso(date_iso: str | None) -> tuple[int, int] | None:
    if not date_iso:
        return None
    try:
        parsed = datetime.strptime(date_iso[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return parsed.year, parsed.month


def month_label(year: int, month: int) -> str:
    return datetime(year, month, 1).strftime("%B %Y")


def month_key_from_raw(raw: str) -> tuple[int, int] | None:
    if not raw.strip():
        return None
    try:
        date_iso = parse_date(raw)
    except ValueError:
        return None
    return month_key_from_iso(date_iso)


def discover_months(files: list[StatementFile]) -> list[tuple[int, int]]:
    months: set[tuple[int, int]] = set()
    for statement in files:
        date_col = statement.mapping.get("date")
        if not date_col:
            continue
        for row in statement.rows:
            month_key = month_key_from_raw(str(row.get(date_col, "")))
            if month_key:
                months.add(month_key)
    return sorted(months, reverse=True)


def format_date_display(date_iso: str | None) -> str:
    if not date_iso:
        return ""
    try:
        parsed = datetime.strptime(date_iso[:10], "%Y-%m-%d")
    except ValueError:
        return date_iso[:10]
    return parsed.strftime("%m/%d/%Y")


def split_mode_label(mode: SplitMode, partner_name: str = "Partner") -> str:
    if mode is SplitMode.HALF:
        return "Split 50/50"
    if mode is SplitMode.WIFE_OWES_FULL:
        first = partner_name.split()[0] if partner_name.strip() else "Partner"
        return f"{first} owes full"
    return "Skip"


def row_had_explicit_split(row: dict[str, str], mapping: dict[str, str | None]) -> bool:
    split_col = mapping.get("split")
    if not split_col:
        return False
    return bool(str(row.get(split_col, "")).strip())


def infer_split_mode(
    description: str,
    *,
    partner_name: str,
    default: SplitMode,
) -> SplitMode:
    if not description.strip():
        return default

    desc_lower = description.lower()
    partner_lower = partner_name.lower().strip()
    first_name = partner_lower.split()[0] if partner_lower else ""

    if first_name and first_name in desc_lower:
        return SplitMode.WIFE_OWES_FULL

    if first_name:
        for hint in TRANSFER_HINTS:
            if hint in desc_lower and first_name in desc_lower:
                return SplitMode.WIFE_OWES_FULL

    return default


def extract_transactions(
    files: list[StatementFile],
    *,
    selected_months: set[tuple[int, int]],
    default_currency: str,
    default_group_id: int,
    default_split: SplitMode,
    partner_name: str,
    bank_mode: bool,
) -> list[Transaction]:
    if not selected_months:
        raise ValueError("Select at least one month.")

    extracted: list[Transaction] = []
    row_counter = 0

    for statement in files:
        transactions = parse_transactions(
            statement.rows,
            statement.mapping,
            default_currency=default_currency,
            default_group_id=default_group_id,
            default_split=default_split,
            bank_mode=bank_mode,
        )

        for transaction in transactions:
            if transaction.split_mode is SplitMode.SKIP:
                continue

            month_key = month_key_from_iso(transaction.date)
            if month_key is None or month_key not in selected_months:
                continue

            source_row = statement.rows[transaction.row_num - 1]
            if not row_had_explicit_split(source_row, statement.mapping):
                transaction.split_mode = infer_split_mode(
                    transaction.description,
                    partner_name=partner_name,
                    default=default_split,
                )

            row_counter += 1
            extracted.append(
                Transaction(
                    row_num=row_counter,
                    description=transaction.description,
                    cost=transaction.cost,
                    date=transaction.date,
                    currency=transaction.currency,
                    notes=transaction.notes,
                    group_id=transaction.group_id,
                    split_mode=transaction.split_mode,
                )
            )

    extracted.sort(key=lambda item: (item.date or "", item.row_num))
    for index, transaction in enumerate(extracted, start=1):
        transaction.row_num = index

    return extracted
