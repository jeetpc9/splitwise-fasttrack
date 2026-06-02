# Splitwise FastTrack

Bulk import expenses into [Splitwise](https://www.splitwise.com) — from CSV or straight from your browser while you shop.

Built for a household group (you + partner): each expense can be **split 50/50** or **partner owes the full amount**. INR-first workflow.

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
