from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime
from pathlib import Path

from splitwise_bulk.settings import load_app_env

from splitwise_bulk.api import SplitwiseClient, SplitwiseError
from splitwise_bulk.csv_parser import auto_detect_mapping, load_csv, parse_transactions
from splitwise_bulk.importer import import_transactions
from splitwise_bulk.models import GroupContext, RowStatus, SplitMode


def _load_env() -> None:
    load_app_env()


def _get_api_key(explicit: str | None) -> str:
    api_key = explicit or os.getenv("SPLITWISE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "Missing API key. Set SPLITWISE_API_KEY in .env or pass --api-key.\n"
            "Get one at https://secure.splitwise.com/apps"
        )
    return api_key


def cmd_verify(args: argparse.Namespace) -> int:
    client = SplitwiseClient(_get_api_key(args.api_key))
    user = client.get_current_user()
    name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
    print(f"Connected as {name} ({user.get('email', '')})")
    return 0


def cmd_groups(args: argparse.Namespace) -> int:
    client = SplitwiseClient(_get_api_key(args.api_key))
    groups = client.get_groups()
    if not groups:
        print("No groups found.")
        return 0
    print(f"{'ID':<10} Name")
    print("-" * 40)
    for group in groups:
        print(f"{group['id']:<10} {group['name']}")
    return 0


def _split_mode_from_args(args: argparse.Namespace) -> SplitMode:
    if args.split_mode == "wife_owes_full":
        return SplitMode.WIFE_OWES_FULL
    return SplitMode.HALF


def cmd_import(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv).expanduser().resolve()
    if not csv_path.exists():
        raise SystemExit(f"CSV file not found: {csv_path}")

    default_group_id = args.group_id
    if default_group_id is None:
        default_group_id = int(os.getenv("SPLITWISE_DEFAULT_GROUP_ID", "0"))

    default_currency = (args.currency or os.getenv("SPLITWISE_DEFAULT_CURRENCY", "USD")).upper()
    default_split = _split_mode_from_args(args)

    headers, rows = load_csv(csv_path)
    mapping = auto_detect_mapping(headers)

    if args.show_mapping:
        print("Detected column mapping:")
        for field, column in mapping.items():
            print(f"  {field}: {column or '(not mapped)'}")
        print()

    if not mapping.get("cost") and not mapping.get("debit"):
        raise SystemExit("Could not find an amount column. Expected headers like: amount, debit, cost")
    if not mapping.get("description"):
        print("Warning: no description column found; rows will use generic names.")

    transactions = parse_transactions(
        rows,
        mapping,
        default_currency=default_currency,
        default_group_id=default_group_id,
        default_split=default_split,
        bank_mode=args.bank_mode,
    )

    client = None
    group_context = None
    if not args.dry_run:
        client = SplitwiseClient(_get_api_key(args.api_key))
        user = client.get_current_user()
        if default_split is SplitMode.WIFE_OWES_FULL or any(
            t.split_mode is SplitMode.WIFE_OWES_FULL for t in transactions
        ):
            if args.partner_id is None:
                raise SystemExit("--partner-id is required for wife-owes-full splits.")
            group_context = GroupContext(
                group_id=default_group_id,
                current_user_id=int(user["id"]),
                partner_user_id=args.partner_id,
                partner_name="partner",
            )

    mode = "DRY RUN" if args.dry_run else "LIVE IMPORT"
    print(f"{mode}: processing {len(transactions)} rows...")
    print(f"  Group ID: {default_group_id}")
    print(f"  Default split: {default_split.label}")
    print(f"  Bank mode: {args.bank_mode}")
    print()

    results = import_transactions(
        transactions,
        client,
        dry_run=args.dry_run,
        group_context=group_context,
    )

    counts = {status: 0 for status in RowStatus}
    for result in results:
        counts[result.status] += 1
        icon = {
            RowStatus.SUCCESS: "✓",
            RowStatus.DRY_RUN: "~",
            RowStatus.SKIPPED: "-",
            RowStatus.ERROR: "✗",
        }[result.status]
        print(
            f"  {icon} Row {result.row:>3}: {result.description[:36]:<36} "
            f"{result.cost:>8}  [{result.split_mode}] {result.message}"
        )

    print()
    print(
        f"Done — {counts[RowStatus.SUCCESS] + counts[RowStatus.DRY_RUN]} ok, "
        f"{counts[RowStatus.ERROR]} errors, {counts[RowStatus.SKIPPED]} skipped"
    )

    if args.output or not args.dry_run:
        output_path = Path(args.output).expanduser() if args.output else (
            csv_path.parent / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["row", "description", "cost", "date", "split_mode", "status", "message"],
            )
            writer.writeheader()
            writer.writerows(result.as_dict() for result in results)
        print(f"Results written to {output_path}")

    return 1 if counts[RowStatus.ERROR] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="splitwise-bulk",
        description="Bulk upload transactions from CSV to Splitwise.",
    )
    parser.add_argument(
        "--api-key",
        help="Splitwise OAuth access token (overrides SPLITWISE_API_KEY env var)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify", help="Verify API key and show current user")
    verify.set_defaults(func=cmd_verify)

    groups = subparsers.add_parser("groups", help="List your Splitwise groups")
    groups.set_defaults(func=cmd_groups)

    import_cmd = subparsers.add_parser("import", help="Import transactions from a CSV file")
    import_cmd.add_argument("csv", help="Path to CSV file")
    import_cmd.add_argument("--group-id", type=int, default=None, help="Splitwise group ID")
    import_cmd.add_argument("--partner-id", type=int, help="Partner user ID for full-owe splits")
    import_cmd.add_argument("--currency", help="Default currency (default: USD)")
    import_cmd.add_argument(
        "--split-mode",
        choices=["half", "wife_owes_full"],
        default="half",
        help="Default split when CSV has no split column",
    )
    import_cmd.add_argument(
        "--bank-mode",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Treat signed amounts as bank exports (default: true)",
    )
    import_cmd.add_argument("--dry-run", action="store_true", help="Preview without posting")
    import_cmd.add_argument("--show-mapping", action="store_true", help="Print column mapping")
    import_cmd.add_argument("--output", "-o", help="Write results CSV")
    import_cmd.set_defaults(func=cmd_import)

    return parser


def main() -> None:
    _load_env()
    parser = build_parser()
    args = parser.parse_args()
    try:
        raise SystemExit(args.func(args))
    except SplitwiseError as exc:
        raise SystemExit(f"Splitwise error: {exc}") from exc


if __name__ == "__main__":
    main()
