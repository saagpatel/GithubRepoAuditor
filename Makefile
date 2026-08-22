.PHONY: install install-dev doctor audit control-center demo benchmark workbook-gate workbook-signoff test lint format type-check run clean release-gate build shiv dist-check release publish-pypi

PYTHON := python3
SOURCE_ENV := PYTHONPATH=src
CLI := $(SOURCE_ENV) uv run python -m github_repo_auditor.cli
USERNAME ?= saagpatel
ARGS ?=

install:
	$(PYTHON) -m pip install -e ".[config]"

install-dev:
	$(PYTHON) -m pip install -e ".[dev,config]"

doctor:
	$(CLI) $(USERNAME) --doctor $(ARGS)

audit:
	$(CLI) $(USERNAME) --excel-mode standard $(ARGS)

control-center:
	$(CLI) $(USERNAME) --control-center $(ARGS)

demo:
	$(PYTHON) scripts/build_demo_artifacts.py

benchmark:
	$(PYTHON) scripts/benchmark_large_portfolio.py

workbook-gate:
	$(SOURCE_ENV) $(PYTHON) -m github_repo_auditor.workbook_gate $(ARGS)

workbook-signoff:
	$(SOURCE_ENV) $(PYTHON) -m github_repo_auditor.workbook_gate --record-signoff $(ARGS)

test:
	$(SOURCE_ENV) $(PYTHON) -m pytest tests/ -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

type-check:
	mypy src/ --ignore-missing-imports

run:
	$(CLI) --help

release-gate:
	@echo "=== Running release gate: mutation testing ==="
	@echo "Requires: Python 3.13 and the locked dev environment"
	$(SOURCE_ENV) uv run --extra dev --python 3.13 mutmut run
	@echo ""
	@echo "=== Mutation results ==="
	uv run --no-sync python scripts/check_mutation_score.py --minimum 0.85

clean:
	rm -rf .pytest_cache __pycache__ dist build *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +

# ── Distribution targets ────────────────────────────────────────────────────

build:
	@echo "=== Building wheel + sdist ==="
	$(PYTHON) -m build
	@echo "=== Build complete: dist/ ==="

dist-check:
	@echo "=== Running twine check ==="
	$(PYTHON) -m twine check dist/*

shiv:
	@echo "=== Building shiv single-file binary ==="
	@command -v shiv >/dev/null 2>&1 || { echo "shiv not installed — run: pip install shiv"; exit 1; }
	@mkdir -p dist
	shiv -c audit -o dist/audit.pyz . --python "/usr/bin/env python3"
	@echo "=== dist/audit.pyz ready. Test: ./dist/audit.pyz --help ==="

release: build dist-check shiv
	@echo "=== Release artifacts are ready in dist/ ==="
	@echo "Tag a v* release to publish GitHub Release assets. Use make publish-pypi only after PyPI trusted publishing or credentials are configured."

publish-pypi:
	@echo "=== Publishing wheel + sdist to PyPI via scripts/release.sh ==="
	bash scripts/release.sh --publish-pypi
