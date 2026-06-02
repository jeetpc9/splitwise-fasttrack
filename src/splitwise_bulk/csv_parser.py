from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

from splitwise_bulk.models import SplitMode, Transaction

# Common headers from Chase, Amex, BofA, Citi, Capital One, etc.
KNOWN_ALIASES = {
    "date": [
        "date",
        "transaction date",
        "trans date",
        "posted date",
        "post date",
        "posting date",
        "transaction_date",
        "post_date",
    ],
    "description": [
        "description",
        "desc",
        "memo",
        "note",
        "merchant",
        "name",
        "payee",
        "details",
        "transaction description",
        "merchant name",
        "original description",
    ],
    "cost": [
        "cost",
        "amount",
        "total",
        "price",
        "charge",
        "transaction amount",
        "transaction",
    ],
    "debit": ["debit", "withdrawal", "withdrawals", "debit amount", "money out"],
    "credit": ["credit", "deposit", "deposits", "credit amount", "money in"],
    "currency": ["currency", "currency code", "ccy"],
    "category": ["category", "cat", "type", "expense type", "transaction type"],
    "group_id": ["group_id", "group id", "group", "splitwise group"],
    "notes": ["notes", "note", "comment", "comments", "memo2", "reference"],
    "split": ["split", "split mode", "splitwise split", "who pays", "share"],
}

DATE_FORMATS = (
    "%d/%m/%y",   # 03/04/26 (DD/MM/YY — default CSV format)
    "%d/%m/%Y",   # 03/04/2026
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d-%m-%y",
    "%m/%d/%y",
    "%Y-%m-%d %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
)

# Bank/credit-card rows that are usually not shared expenses.
AUTO_SKIP_PATTERNS = re.compile(
    r"\b("
    r"payment|autopay|auto pay|credit card payment|cc payment|"
    r"transfer|online payment|pay bill|balance transfer|"
    r"interest charge|finance charge|annual fee|late fee|"
    r"reward|cashback|cash back|refund|credit adjustment"
    r")\b",
    re.IGNORECASE,
)


def load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        if not headers:
            raise ValueError("CSV file has no headers.")
        rows = [dict(row) for row in reader]
    return headers, rows


def auto_detect_mapping(headers: list[str]) -> dict[str, str | None]:
    header_norm = {header.lower().strip(): header for header in headers}
    mapping: dict[str, str | None] = {}
    for field, aliases in KNOWN_ALIASES.items():
        mapping[field] = None
        for alias in aliases:
            if alias in header_norm:
                mapping[field] = header_norm[alias]
                break

    # Prefer debit column over generic amount when both exist (common in bank exports).
    if mapping.get("debit") and mapping.get("cost") == mapping.get("debit"):
        pass
    elif mapping.get("debit") and not mapping.get("cost"):
        mapping["cost"] = mapping["debit"]

    return mapping


def parse_amount(raw: str, *, bank_mode: bool = False) -> str:
    cleaned = raw.replace("$", "").replace(",", "").replace("(", "-").replace(")", "").strip()
    if not cleaned:
        raise ValueError("Amount is empty.")
    value = float(cleaned)
    if value == 0:
        raise ValueError("Amount is zero.")
    if bank_mode:
        if value > 0:
            raise ValueError("Positive amount (credit/payment) — skipped in bank mode.")
        value = abs(value)
    elif value < 0:
        value = abs(value)
    return f"{value:.2f}"


def parse_amount_from_row(
    row: dict[str, str],
    mapping: dict[str, str | None],
    *,
    bank_mode: bool,
) -> str:
    debit_col = mapping.get("debit")
    credit_col = mapping.get("credit")
    cost_col = mapping.get("cost")

    if debit_col or credit_col:
        debit_raw = str(row.get(debit_col or "", "")).strip() if debit_col else ""
        credit_raw = str(row.get(credit_col or "", "")).strip() if credit_col else ""
        if debit_raw:
            return parse_amount(debit_raw, bank_mode=False)
        if credit_raw:
            raise ValueError("Credit/deposit row — skipped.")
        raise ValueError("Missing debit amount.")

    if not cost_col:
        raise ValueError("No amount column mapped.")

    return parse_amount(str(row.get(cost_col, "")).strip(), bank_mode=bank_mode)


def should_auto_skip(description: str, *, bank_mode: bool) -> str | None:
    if not bank_mode:
        return None
    if AUTO_SKIP_PATTERNS.search(description):
        return "Auto-skipped bank payment/credit row."
    return None


def parse_date(raw: str) -> str | None:
    if not raw.strip():
        return None
    cleaned = raw.strip().split(" ")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {raw!r}")


def parse_transactions(
    rows: list[dict[str, str]],
    mapping: dict[str, str | None],
    *,
    default_currency: str,
    default_group_id: int,
    default_split: SplitMode = SplitMode.HALF,
    bank_mode: bool = True,
) -> list[Transaction]:
    transactions: list[Transaction] = []

    for index, row in enumerate(rows, start=1):
        def get(field: str) -> str:
            column = mapping.get(field)
            if not column:
                return ""
            return str(row.get(column, "")).strip()

        description = get("description") or f"Expense #{index}"
        split_raw = get("split")

        try:
            split_mode = SplitMode.from_text(split_raw, default_split)
        except ValueError as exc:
            raise ValueError(f"Row {index}: {exc}") from exc

        if split_mode is SplitMode.SKIP:
            transactions.append(
                Transaction(
                    row_num=index,
                    description=description,
                    cost="0.00",
                    group_id=default_group_id,
                    split_mode=SplitMode.SKIP,
                )
            )
            continue

        skip_reason = should_auto_skip(description, bank_mode=bank_mode)
        if skip_reason:
            transactions.append(
                Transaction(
                    row_num=index,
                    description=description,
                    cost="0.00",
                    group_id=default_group_id,
                    split_mode=SplitMode.SKIP,
                    notes=skip_reason,
                )
            )
            continue

        try:
            cost = parse_amount_from_row(row, mapping, bank_mode=bank_mode)
        except ValueError as exc:
            message = str(exc)
            if "skipped" in message.lower():
                transactions.append(
                    Transaction(
                        row_num=index,
                        description=description,
                        cost="0.00",
                        group_id=default_group_id,
                        split_mode=SplitMode.SKIP,
                        notes=message,
                    )
                )
                continue
            raise ValueError(f"Row {index}: {message}") from exc

        date_raw = get("date")
        date_iso = parse_date(date_raw) if date_raw else None
        currency = get("currency") or default_currency
        notes = get("notes") or None

        group_id = default_group_id
        group_raw = get("group_id")
        if group_raw:
            group_id = int(group_raw)

        transactions.append(
            Transaction(
                row_num=index,
                description=description,
                cost=cost,
                date=date_iso,
                currency=currency.upper(),
                notes=notes,
                group_id=group_id,
                split_mode=split_mode,
            )
        )

    return transactions
