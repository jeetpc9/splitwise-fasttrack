from __future__ import annotations

from pathlib import Path

from splitwise_bulk.csv_parser import load_csv, parse_date
from splitwise_bulk.models import SplitMode, Transaction

CURRENCY = "INR"

# Expected CSV columns (header names are matched case-insensitively).
COLUMN_ALIASES = {
    "date": ["date"],
    "description": ["description", "desc"],
    "amount": ["amount", "amont"],
    "split": [
        "type of split",
        "type_of_split",
        "split type",
        "split",
        "split_type",
    ],
}


def _normalize_header(header: str) -> str:
    return header.lower().strip()


def _map_columns(headers: list[str]) -> dict[str, str]:
    normalized = {_normalize_header(header): header for header in headers}
    mapping: dict[str, str] = {}
    missing: list[str] = []

    for field, aliases in COLUMN_ALIASES.items():
        found = None
        for alias in aliases:
            if alias in normalized:
                found = normalized[alias]
                break
        if found:
            mapping[field] = found
        else:
            missing.append(field)

    if missing:
        expected = "date, description, amount, type of split"
        raise ValueError(
            f"Missing required column(s): {', '.join(missing)}.\n"
            f"Expected headers like: {expected}"
        )
    return mapping


def _parse_amount_inr(raw: str, *, row_num: int) -> str:
    cleaned = raw.replace("₹", "").replace(",", "").replace(" ", "").strip()
    if not cleaned:
        raise ValueError(f"Row {row_num}: amount is empty.")
    try:
        value = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"Row {row_num}: invalid amount {raw!r}.") from exc
    if value <= 0:
        raise ValueError(f"Row {row_num}: amount must be a positive number (INR).")
    return f"{value:.2f}"


def parse_expense_csv(path: Path, *, default_group_id: int = 0) -> list[Transaction]:
    headers, rows = load_csv(path)
    if not rows:
        raise ValueError(f"{path.name}: CSV has no data rows.")

    mapping = _map_columns(headers)
    transactions: list[Transaction] = []

    for index, row in enumerate(rows, start=1):
        date_raw = str(row.get(mapping["date"], "")).strip()
        description = str(row.get(mapping["description"], "")).strip()
        amount_raw = str(row.get(mapping["amount"], "")).strip()
        split_raw = str(row.get(mapping["split"], "")).strip()

        if not description:
            raise ValueError(f"Row {index}: description is empty.")

        split_mode = SplitMode.from_text(split_raw or "split_half", SplitMode.HALF)
        if split_mode is SplitMode.SKIP:
            continue

        cost = _parse_amount_inr(amount_raw, row_num=index)
        if not date_raw:
            raise ValueError(f"Row {index}: date is empty.")
        try:
            date_iso = parse_date(date_raw)
        except ValueError as exc:
            raise ValueError(f"Row {index}: {exc}") from exc

        transactions.append(
            Transaction(
                row_num=index,
                description=description,
                cost=cost,
                date=date_iso,
                currency=CURRENCY,
                group_id=default_group_id,
                split_mode=split_mode,
            )
        )

    return transactions


def split_mode_csv_value(mode: SplitMode) -> str:
    if mode is SplitMode.WIFE_OWES_FULL:
        return "full_other"
    return "split_half"
