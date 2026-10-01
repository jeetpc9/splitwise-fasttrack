# Splitwise FastTrack

An INR-first desktop tool for moving household expenses from CSV files and supported shopping sites into [Splitwise](https://www.splitwise.com), with a review step before upload.

## The problem

A purchase is already recorded in an order history or bank export, but sharing the expense can mean entering the same details again. For a two-person household, the recurring decision is often simple: split the cost equally, or assign the full amount to the other person.

FastTrack brings those records into one review workflow.

## Product scope and choices

- **A narrow household workflow.** The primary use case is a two-person group, with 50/50 and full-other split modes.
- **Two ways to bring expenses in.** CSV handles batches; a Tampermonkey script brings supported browser orders into the desktop app.
- **Review before upload.** Users can inspect and edit expenses before sending them to Splitwise.
- **A local desktop workflow.** A small listener on `127.0.0.1:8765` receives browser orders. The Python client sends expense requests to Splitwise.
- **A repeatable command-line path.** The CLI supports dry runs and reports a result for each transaction.

## How it works

```text
CSV file ----------------------+
                               |
Supported order-history page   |
  -> Tampermonkey script       |
  -> Local order listener -----+-> Review and edit -> Splitwise API
```

The implementation uses Python 3.10+, Requests, and python-dotenv, with a JavaScript userscript for browser ingestion. The repository includes a macOS app launcher.

## Current status

Personal utility, marked alpha in the package metadata. The repository contains the import workflow, desktop interface, CLI, and browser integration. Compatibility with current merchant pages and live Splitwise uploads should be checked in your own environment.

Browser ingestion checks incoming orders against known keys based on source, date, description, and amount. This is not a guarantee against duplicate expenses across repeated uploads.

## What to validate next

- Compare the time required to record a batch manually with the review-and-upload workflow.
- Track how often extracted dates, descriptions, or amounts need correction.
- Test repeat imports and recovery after partial upload failures.
- Add a short walkthrough using sample expenses so the workflow is visible before installation.

These are proposed validation steps; no measured time savings or adoption results are claimed.

## Quick start

```bash
git clone https://github.com/jeetpc9/splitwise-fasttrack.git
cd splitwise-fasttrack
./scripts/setup.sh
cp .env.example .env   # add SPLITWISE_API_KEY
make app               # creates Splitwise FastTrack.app (one-click launch)
```

Or run from terminal: `make gui`

## Features

- **Desktop app** — Browser Sync tab + CSV Upload tab, review/edit, confirm upload
- **Tampermonkey sync** — Amazon, Apollo Pharmacy, Urban Company orders auto-send to the app
- **Fixed CSV format** — `date` (DD/MM/YY), `description`, `amount` (INR), `type of split`
- **Split modes** — `split_half` (50/50) or `full_other` (partner owes all)
- **Apple Silicon native** — arm64 launcher, no Rosetta required
- CLI for scripting and dry runs

## Browser sync

1. Install `tampermonkey/splitwise-order-export.user.js` in Tampermonkey
2. Launch **Splitwise FastTrack** (keeps localhost listener on port 8765)
3. Open order history (e.g. [amazon.in/your-orders/orders](https://www.amazon.in/your-orders/orders))
4. Orders appear in the **Browser Sync** tab — review and upload

## CSV format

| Column | Example | Notes |
|--------|---------|-------|
| date | `03/04/26` | DD/MM/YY |
| description | `Groceries` | |
| amount | `450.00` | INR |
| type of split | `split_half` | or `full_other` |

See `sample_expenses.csv`.

## Get your API key

1. [https://secure.splitwise.com/apps](https://secure.splitwise.com/apps)
2. Register an app (`http://localhost` for URLs)
3. Use the OAuth test flow → copy the access token
4. Paste into the app (saved locally in `~/.splitwise_bulk_settings.json`)

## CLI

```bash
splitwise-fasttrack          # GUI
splitwise-bulk verify
splitwise-bulk import sample_expenses.csv --group-id YOUR_GROUP_ID --dry-run
```

## Environment variables

| Variable | Description |
|----------|-------------|
| `SPLITWISE_API_KEY` | OAuth access token |
| `SPLITWISE_DEFAULT_GROUP_ID` | Default group ID |

## Project layout

```
splitwise-fasttrack/
├── src/splitwise_bulk/       # App source
├── tampermonkey/             # Browser sync script
├── scripts/
│   ├── setup.sh
│   └── create-macos-app.sh   # Builds Splitwise FastTrack.app
└── sample_expenses.csv
```

## Notes

- Always dry-run first on a new CSV export.
- Personal / non-commercial use per [Splitwise API Terms](https://dev.splitwise.com/).
