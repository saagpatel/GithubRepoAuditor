.PHONY: setup check check-python check-web require-tools install install-dev doctor audit control-center demo benchmark workbook-gate workbook-signoff test lint format type-check run clean release-gate build shiv dist-check release publish-pypi
.DEFAULT_GOAL := install

PYTHON := uv run --locked python
MYPY_MODULES := src/github_repo_auditor/operator_resolution_trend.py src/github_repo_auditor/operator_trend_support.py src/github_repo_auditor/operator_trend_pending_text.py src/github_repo_auditor/operator_trend_pending_debt.py src/github_repo_auditor/operator_trend_transition_closure.py src/github_repo_auditor/operator_trend_decision_memory.py src/github_repo_auditor/operator_trend_recommendation_drift.py src/github_repo_auditor/operator_trend_confidence_calibration.py src/github_repo_auditor/operator_trend_trust_policy_history.py src/github_repo_auditor/operator_trend_exception_recovery.py src/github_repo_auditor/operator_trend_class_transitions.py src/github_repo_auditor/operator_trend_run_context.py src/github_repo_auditor/operator_trend_summary_context.py src/github_repo_auditor/operator_trend_apply_chain.py src/github_repo_auditor/operator_trend_topline_payload.py
SOURCE_ENV := PYTHONPATH=src
CLI := $(SOURCE_ENV) uv run python -m github_repo_auditor.cli
USERNAME ?= saagpatel
ARGS ?=

# Setup hints are checked before any tools run. Checks do not regenerate outputs.
require-tools:
	@command -v uv >/dev/null 2>&1 || { echo "Missing uv. Install uv 0.13.0, then run make setup."; exit 1; }

setup: require-tools
	@command -v pnpm >/dev/null 2>&1 || { echo "Missing pnpm. Install the Node and pnpm pins in web/, then run make setup."; exit 1; }
	uv sync --locked --extra dev --extra serve --extra config --extra build
	pnpm --dir web install --frozen-lockfile

check: check-python check-web

check-python: require-tools
	uv run --locked --extra dev ruff check src/ tests/
	uv run --locked --extra dev ruff format --check src/ tests/
	uv run --locked --extra dev mypy $(MYPY_MODULES)
	uv run --locked python scripts/generate_portfolio_truth_contract_fixture.py --check
	uv run --locked --extra dev --extra serve --extra config --extra build pytest -q -k 'not semantic_index'

check-web:
	@command -v pnpm >/dev/null 2>&1 || { echo "Missing pnpm. Install the Node and pnpm pins in web/, then run make setup."; exit 1; }
	@test -d web/node_modules || { echo "Missing web dependencies. Run make setup."; exit 1; }
	pnpm --dir web typecheck
	pnpm --dir web lint
	pnpm --dir web test
	pnpm --dir web build

install: require-tools
	uv sync --locked --extra config

install-dev: require-tools
	uv sync --locked --extra dev --extra serve --extra config --extra build

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
	uv run --locked --extra dev ruff check src/ tests/

format:
	uv run --locked --extra dev ruff format src/ tests/

type-check:
	uv run --locked --extra dev mypy $(MYPY_MODULES)

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
	uv run --locked --extra build python -m build
	@echo "=== Build complete: dist/ ==="

dist-check:
	@echo "=== Running twine check ==="
	uv run --locked --extra build python -m twine check dist/*.whl dist/*.tar.gz

shiv: build
	@echo "=== Building shiv single-file binary ==="
	@mkdir -p dist
	uv export --locked --no-dev --extra config --no-emit-project --no-hashes -o dist/shiv-requirements.txt
	uv run --locked --extra build shiv -c audit -o dist/audit.pyz -r dist/shiv-requirements.txt --no-deps dist/*.whl --python "/usr/bin/env python3"
	@echo "=== dist/audit.pyz ready. Test: ./dist/audit.pyz --help ==="

release: build dist-check shiv
	@echo "=== Release artifacts are ready in dist/ ==="
	@echo "Tag a v* release to publish GitHub Release assets. Use make publish-pypi only after PyPI trusted publishing or credentials are configured."

publish-pypi:
	@echo "=== Publishing wheel + sdist to PyPI via scripts/release.sh ==="
	bash scripts/release.sh --publish-pypi
