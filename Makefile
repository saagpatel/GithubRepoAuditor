.PHONY: install install-dev doctor audit control-center demo benchmark workbook-gate workbook-signoff test lint format type-check run clean release-gate build shiv dist-check release publish-pypi

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
	audit $(USERNAME) --excel-mode standard $(ARGS)

control-center:
	audit $(USERNAME) --control-center $(ARGS)

demo:
	$(PYTHON) scripts/build_demo_artifacts.py

benchmark:
	$(PYTHON) scripts/benchmark_large_portfolio.py

workbook-gate:
	$(PYTHON) -m src.workbook_gate $(ARGS)

workbook-signoff:
	$(PYTHON) -m src.workbook_gate --record-signoff $(ARGS)

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

release-gate:
	@echo "=== Running release gate: mutation testing ==="
	@echo "Requires: python3.13, mutmut 2.x installed in python3.13 environment"
	rm -rf .mutmut-cache mutants/
	python3.13 -m mutmut run
	@echo ""
	@echo "=== Mutation results ==="
	python3.13 -c "\
import sqlite3; \
conn = sqlite3.connect('.mutmut-cache'); \
rows = conn.execute('SELECT status, count(*) FROM Mutant GROUP BY status').fetchall(); \
total = sum(r[1] for r in rows); \
killed = next((r[1] for r in rows if r[0] == 'ok_killed'), 0); \
survived = next((r[1] for r in rows if r[0] == 'bad_survived'), 0); \
timeout = next((r[1] for r in rows if r[0] == 'bad_timeout'), 0); \
denom = killed + survived; \
rate = killed / denom if denom > 0 else 0.0; \
print(f'Total: {total} | Killed: {killed} | Survived: {survived} | Timeout: {timeout}'); \
print(f'Kill rate: {rate:.1%}'); \
exit(0 if rate >= 0.85 else 1)"

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
