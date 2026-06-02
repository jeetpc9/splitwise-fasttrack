from __future__ import annotations

from splitwise_bulk.api import SplitwiseClient, SplitwiseError
from splitwise_bulk.models import GroupContext, ImportResult, RowStatus, SplitMode, Transaction


def build_expense_payload(
    transaction: Transaction,
    *,
    group_context: GroupContext | None,
) -> dict[str, str]:
    if transaction.split_mode is SplitMode.SKIP:
        raise ValueError("Cannot build payload for skipped transaction.")

    payload: dict[str, str] = {
        "cost": transaction.cost,
        "description": transaction.description,
        "currency_code": transaction.currency,
        "group_id": str(transaction.group_id or 0),
    }
    if transaction.date:
        payload["date"] = transaction.date
    if transaction.notes:
        payload["details"] = transaction.notes

    if transaction.split_mode is SplitMode.HALF:
        payload["split_equally"] = "true"
        return payload

    if transaction.split_mode is SplitMode.WIFE_OWES_FULL:
        if group_context is None:
            raise SplitwiseError("Other group member is required for full_other splits.")
        cost = transaction.cost
        payload.update(
            {
                "users__0__user_id": str(group_context.current_user_id),
                "users__0__paid_share": cost,
                "users__0__owed_share": "0.00",
                "users__1__user_id": str(group_context.partner_user_id),
                "users__1__paid_share": "0.00",
                "users__1__owed_share": cost,
            }
        )
        return payload

    raise ValueError(f"Unsupported split mode: {transaction.split_mode}")


def import_transactions(
    transactions: list[Transaction],
    client: SplitwiseClient | None,
    *,
    dry_run: bool,
    group_context: GroupContext | None,
) -> list[ImportResult]:
    results: list[ImportResult] = []

    for transaction in transactions:
        date_display = (transaction.date or "").replace("T", " ").replace("Z", "")
        split_label = transaction.split_mode.label

        if transaction.split_mode is SplitMode.SKIP:
            message = transaction.notes or "Skipped"
            results.append(
                ImportResult(
                    row=transaction.row_num,
                    description=transaction.description,
                    cost=transaction.cost,
                    date=date_display,
                    status=RowStatus.SKIPPED,
                    message=message,
                    split_mode=split_label,
                )
            )
            continue

        try:
            if dry_run:
                results.append(
                    ImportResult(
                        row=transaction.row_num,
                        description=transaction.description,
                        cost=transaction.cost,
                        date=date_display,
                        status=RowStatus.DRY_RUN,
                        message=f"OK — {split_label} (not sent)",
                        split_mode=split_label,
                    )
                )
                continue

            if client is None:
                raise SplitwiseError("Splitwise client is required for live imports.")

            payload = build_expense_payload(transaction, group_context=group_context)
            client.create_expense(payload)
            results.append(
                ImportResult(
                    row=transaction.row_num,
                    description=transaction.description,
                    cost=transaction.cost,
                    date=date_display,
                    status=RowStatus.SUCCESS,
                    message=f"Imported — {split_label}",
                    split_mode=split_label,
                )
            )
        except (SplitwiseError, ValueError) as exc:
            results.append(
                ImportResult(
                    row=transaction.row_num,
                    description=transaction.description,
                    cost=transaction.cost,
                    date=date_display,
                    status=RowStatus.ERROR,
                    message=str(exc),
                    split_mode=split_label,
                )
            )

    return results
