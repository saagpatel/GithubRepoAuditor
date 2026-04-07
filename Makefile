.PHONY: install install-dev doctor audit control-center test lint format type-check run clean

PYTHON := python3
USERNAME ?= saagpatel
ARGS ?=

install:
	$(PYTHON) -m pip install -e ".[config]"

install-dev:
	$(PYTHON) -m pip install -e ".[dev,config]"

doctor:
	audit $(USERNAME) --doctor $(ARGS)

audit:
	audit $(USERNAME) $(ARGS)

control-center:
	audit $(USERNAME) --control-center $(ARGS)

test:
	$(PYTHON) -m pytest tests/ -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

type-check:
	mypy src/ --ignore-missing-imports

run:
	audit --help

clean:
	rm -rf .pytest_cache __pycache__ dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
