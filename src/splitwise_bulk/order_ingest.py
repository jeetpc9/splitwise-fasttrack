from __future__ import annotations

from splitwise_bulk.models import SplitMode, Transaction


def order_key(source: str, date: str, description: str, amount: str) -> str:
    return f"{source}|{date}|{description.strip().lower()}|{amount}"


def orders_to_transactions(
    orders: list[dict],
    *,
    source: str,
    existing_keys: set[str],
    start_row: int,
    default_group_id: int = 0,
) -> tuple[list[Transaction], int, int]:
    """Convert browser JSON payloads into Transaction objects. Returns (new_txns, added, skipped)."""
    added = 0
    skipped = 0
    new_transactions: list[Transaction] = []
    row_num = start_row

    for raw in orders:
        date = str(raw.get("date", "")).strip()
        description = str(raw.get("description", "")).strip()
        amount = str(raw.get("amount", "")).strip()
        split_raw = str(raw.get("split", "split_half")).strip()

        if not description or not amount:
            skipped += 1
            continue

        try:
            value = float(amount.replace(",", ""))
            if value <= 0:
                skipped += 1
                continue
            amount = f"{value:.2f}"
        except ValueError:
            skipped += 1
            continue

        key = order_key(source, date, description, amount)
        if key in existing_keys:
            skipped += 1
            continue

        try:
            split_mode = SplitMode.from_text(split_raw, SplitMode.HALF)
        except ValueError:
            split_mode = SplitMode.HALF

        if split_mode is SplitMode.SKIP:
            skipped += 1
            continue

        date_iso = None
        if date:
            if "T" in date:
                date_iso = date if date.endswith("Z") else f"{date}Z"
            else:
                date_iso = f"{date}T00:00:00Z"

        row_num += 1
        existing_keys.add(key)
        added += 1
        new_transactions.append(
            Transaction(
                row_num=row_num,
                description=description,
                cost=amount,
                date=date_iso,
                currency="INR",
                group_id=default_group_id,
                split_mode=split_mode,
                ingest_key=key,
            )
        )

    return new_transactions, added, skipped
