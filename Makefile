.PHONY: setup install gui cli verify dry-run clean app

PYTHON ?= python3
VENV ?= .venv
BIN = $(VENV)/bin

setup: $(VENV)/bin/activate
	$(BIN)/pip install -e .

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e .

install: setup

gui: setup
	@if [ "$$(uname -m)" = "arm64" ]; then /usr/bin/arch -arm64 $(BIN)/splitwise-bulk-gui; else $(BIN)/splitwise-bulk-gui; fi

app: setup
	./scripts/create-macos-app.sh

cli: setup
	$(BIN)/splitwise-bulk $(ARGS)

verify: setup
	$(BIN)/splitwise-bulk verify

dry-run: setup
	$(BIN)/splitwise-bulk import sample_expenses.csv --group-id 0 --dry-run

clean:
	rm -rf $(VENV) build dist src/*.egg-info .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
