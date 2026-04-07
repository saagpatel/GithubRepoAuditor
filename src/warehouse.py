from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.models import AuditReport

WAREHOUSE_FILENAME = "portfolio-warehouse.db"
WAREHOUSE_SCHEMA_VERSION = 7


def write_warehouse_snapshot(
    report: AuditReport,
    output_dir: Path,
    report_path: Path | None = None,
) -> Path:
    """Persist a warehouse-friendly snapshot for downstream analytics."""
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / WAREHOUSE_FILENAME
    conn = sqlite3.connect(db_path)
    try:
        _ensure_schema(conn)
        _insert_run(conn, report, report_path)
        conn.commit()
    finally:
        conn.close()
    return db_path


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS warehouse_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_runs (
            run_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            scoring_profile TEXT NOT NULL,
            run_mode TEXT NOT NULL,
            report_path TEXT,
            total_repos INTEGER NOT NULL,
            repos_audited INTEGER NOT NULL,
            average_score REAL NOT NULL,
            portfolio_baseline_size INTEGER NOT NULL,
            baseline_signature TEXT NOT NULL DEFAULT '',
            baseline_context_json TEXT NOT NULL DEFAULT '{}',
            tier_distribution_json TEXT NOT NULL,
            language_distribution_json TEXT NOT NULL,
            lens_summary_json TEXT NOT NULL,
            security_summary_json TEXT NOT NULL,
            security_governance_preview_json TEXT NOT NULL,
            collections_json TEXT NOT NULL,
            scenario_summary_json TEXT NOT NULL,
            campaign_summary_json TEXT NOT NULL DEFAULT '{}',
            writeback_preview_json TEXT NOT NULL DEFAULT '{}',
            writeback_results_json TEXT NOT NULL DEFAULT '{}',
            managed_state_drift_json TEXT NOT NULL DEFAULT '[]',
            rollback_preview_json TEXT NOT NULL DEFAULT '{}',
            campaign_history_json TEXT NOT NULL DEFAULT '[]',
            governance_preview_json TEXT NOT NULL DEFAULT '{}',
            governance_approval_json TEXT NOT NULL DEFAULT '{}',
            governance_results_json TEXT NOT NULL DEFAULT '{}',
            governance_history_json TEXT NOT NULL DEFAULT '[]',
            governance_drift_json TEXT NOT NULL DEFAULT '[]',
            governance_summary_json TEXT NOT NULL DEFAULT '{}',
            preflight_summary_json TEXT NOT NULL DEFAULT '{}',
            review_summary_json TEXT NOT NULL DEFAULT '{}',
            review_alerts_json TEXT NOT NULL DEFAULT '[]',
            material_changes_json TEXT NOT NULL DEFAULT '[]',
            review_targets_json TEXT NOT NULL DEFAULT '[]',
            review_history_json TEXT NOT NULL DEFAULT '[]',
            watch_state_json TEXT NOT NULL DEFAULT '{}',
            operator_summary_json TEXT NOT NULL DEFAULT '{}',
            operator_queue_json TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS repos (
            repo_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            full_name TEXT NOT NULL,
            html_url TEXT NOT NULL,
            primary_language TEXT,
            private INTEGER NOT NULL,
            fork INTEGER NOT NULL,
            archived INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS repo_snapshots (
            run_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            overall_score REAL NOT NULL,
            interest_score REAL NOT NULL,
            completeness_tier TEXT NOT NULL,
            interest_tier TEXT NOT NULL,
            grade TEXT NOT NULL,
            interest_grade TEXT NOT NULL,
            badges_json TEXT NOT NULL,
            flags_json TEXT NOT NULL,
            security_posture_json TEXT NOT NULL,
            PRIMARY KEY (run_id, repo_id)
        );

        CREATE TABLE IF NOT EXISTS dimension_scores (
            run_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            dimension TEXT NOT NULL,
            score REAL NOT NULL,
            max_score REAL NOT NULL,
            findings_json TEXT NOT NULL,
            details_json TEXT NOT NULL,
            PRIMARY KEY (run_id, repo_id, dimension)
        );

        CREATE TABLE IF NOT EXISTS lens_scores (
            run_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            lens TEXT NOT NULL,
            score REAL NOT NULL,
            orientation TEXT NOT NULL,
            summary TEXT NOT NULL,
            drivers_json TEXT NOT NULL,
            PRIMARY KEY (run_id, repo_id, lens)
        );

        CREATE TABLE IF NOT EXISTS hotspots (
            run_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            category TEXT NOT NULL,
            severity REAL NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            recommended_action TEXT NOT NULL,
            PRIMARY KEY (run_id, repo_id, category, title)
        );

        CREATE TABLE IF NOT EXISTS security_posture (
            run_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            label TEXT NOT NULL,
            score REAL NOT NULL,
            secrets_found INTEGER NOT NULL,
            dangerous_files_json TEXT NOT NULL,
            has_security_md INTEGER NOT NULL,
            has_dependabot INTEGER NOT NULL,
            evidence_json TEXT NOT NULL,
            PRIMARY KEY (run_id, repo_id)
        );

        CREATE TABLE IF NOT EXISTS security_controls (
            run_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            control_name TEXT NOT NULL,
            status TEXT NOT NULL,
            source TEXT NOT NULL,
            details_json TEXT NOT NULL,
            PRIMARY KEY (run_id, repo_id, control_name)
        );

        CREATE TABLE IF NOT EXISTS security_alerts (
            run_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            open_count INTEGER NOT NULL,
            source TEXT NOT NULL,
            details_json TEXT NOT NULL,
            PRIMARY KEY (run_id, repo_id, alert_type)
        );

        CREATE TABLE IF NOT EXISTS security_providers (
            run_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            provider_name TEXT NOT NULL,
            available INTEGER NOT NULL,
            score REAL,
            details_json TEXT NOT NULL,
            PRIMARY KEY (run_id, repo_id, provider_name)
        );

        CREATE TABLE IF NOT EXISTS security_recommendations (
            run_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            recommendation_key TEXT NOT NULL,
            title TEXT NOT NULL,
            priority TEXT NOT NULL,
            effort TEXT NOT NULL,
            source TEXT NOT NULL,
            expected_posture_lift REAL NOT NULL,
            why TEXT NOT NULL,
            PRIMARY KEY (run_id, repo_id, recommendation_key)
        );

        CREATE TABLE IF NOT EXISTS dependency_inventory (
            run_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            manifest_files_json TEXT NOT NULL,
            dependency_count INTEGER NOT NULL,
            libyears REAL NOT NULL,
            details_json TEXT NOT NULL,
            PRIMARY KEY (run_id, repo_id)
        );

        CREATE TABLE IF NOT EXISTS actions (
            run_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            action_key TEXT NOT NULL,
            title TEXT NOT NULL,
            lens TEXT NOT NULL,
            effort TEXT NOT NULL,
            confidence REAL NOT NULL,
            expected_lens_delta REAL NOT NULL,
            expected_tier_movement TEXT NOT NULL,
            rationale TEXT NOT NULL,
            action_text TEXT NOT NULL,
            PRIMARY KEY (run_id, repo_id, action_key)
        );

        CREATE TABLE IF NOT EXISTS campaign_runs (
            run_id TEXT NOT NULL,
            campaign_type TEXT NOT NULL,
            label TEXT NOT NULL,
            portfolio_profile TEXT NOT NULL,
            collection_name TEXT,
            writeback_target TEXT NOT NULL,
            mode TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            generated_action_ids_json TEXT NOT NULL,
            PRIMARY KEY (run_id, campaign_type)
        );

        CREATE TABLE IF NOT EXISTS action_runs (
            run_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            campaign_type TEXT NOT NULL,
            target TEXT NOT NULL,
            status TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL DEFAULT 'planned',
            reconciliation_outcome TEXT NOT NULL DEFAULT 'preview',
            closed_at TEXT,
            closed_reason TEXT,
            reopened_at TEXT,
            drift_state TEXT,
            rollback_state TEXT,
            PRIMARY KEY (run_id, action_id, target)
        );

        CREATE TABLE IF NOT EXISTS campaign_history (
            run_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            campaign_type TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            reconciliation_outcome TEXT NOT NULL,
            closed_at TEXT,
            closed_reason TEXT,
            reopened_at TEXT,
            supersedes_action_id TEXT,
            superseded_by_action_id TEXT,
            drift_state TEXT,
            rollback_state TEXT,
            details_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (run_id, action_id)
        );

        CREATE TABLE IF NOT EXISTS campaign_target_snapshots (
            run_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            target TEXT NOT NULL,
            status TEXT NOT NULL,
            external_key TEXT,
            before_json TEXT NOT NULL DEFAULT '{}',
            after_json TEXT NOT NULL DEFAULT '{}',
            expected_json TEXT NOT NULL DEFAULT '{}',
            details_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (run_id, action_id, target)
        );

        CREATE TABLE IF NOT EXISTS campaign_drift_events (
            run_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            campaign_type TEXT NOT NULL,
            target TEXT NOT NULL,
            drift_state TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (run_id, action_id, target, drift_state)
        );

        CREATE TABLE IF NOT EXISTS campaign_closure_events (
            run_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            campaign_type TEXT NOT NULL,
            event_type TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (run_id, action_id, event_type)
        );

        CREATE TABLE IF NOT EXISTS rollback_runs (
            run_id TEXT PRIMARY KEY,
            source_run_id TEXT,
            preview_json TEXT NOT NULL DEFAULT '{}',
            results_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'preview'
        );

        CREATE TABLE IF NOT EXISTS governance_approvals (
            source_run_id TEXT PRIMARY KEY,
            approved_at TEXT NOT NULL,
            scope TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            action_count INTEGER NOT NULL,
            applyable_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS governance_runs (
            run_id TEXT PRIMARY KEY,
            source_run_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            status TEXT NOT NULL,
            summary_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS governance_action_results (
            run_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            control_key TEXT NOT NULL,
            status TEXT NOT NULL,
            rollback_state TEXT,
            before_json TEXT NOT NULL DEFAULT '{}',
            after_json TEXT NOT NULL DEFAULT '{}',
            details_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (run_id, action_id)
        );

        CREATE TABLE IF NOT EXISTS governance_drift_events (
            run_id TEXT NOT NULL,
            action_id TEXT,
            repo_id TEXT NOT NULL,
            control_key TEXT,
            drift_type TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (run_id, repo_id, control_key, drift_type)
        );

        CREATE TABLE IF NOT EXISTS github_writebacks (
            run_id TEXT NOT NULL,
            repo_id TEXT NOT NULL,
            target TEXT NOT NULL,
            status TEXT NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            details_json TEXT NOT NULL,
            PRIMARY KEY (run_id, repo_id, target)
        );

        CREATE TABLE IF NOT EXISTS notion_writebacks (
            run_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            status TEXT NOT NULL,
            details_json TEXT NOT NULL,
            PRIMARY KEY (run_id, action_id)
        );

        CREATE TABLE IF NOT EXISTS external_refs (
            run_id TEXT NOT NULL,
            action_id TEXT NOT NULL,
            ref_key TEXT NOT NULL,
            ref_value TEXT NOT NULL,
            PRIMARY KEY (run_id, action_id, ref_key)
        );

        CREATE TABLE IF NOT EXISTS collections (
            run_id TEXT NOT NULL,
            collection_name TEXT NOT NULL,
            repo_name TEXT NOT NULL,
            rank_index INTEGER NOT NULL,
            reason TEXT NOT NULL,
            description TEXT NOT NULL,
            PRIMARY KEY (run_id, collection_name, repo_name)
        );

        CREATE TABLE IF NOT EXISTS profiles (
            run_id TEXT NOT NULL,
            profile_name TEXT NOT NULL,
            description TEXT NOT NULL,
            lens_weights_json TEXT NOT NULL,
            PRIMARY KEY (run_id, profile_name)
        );

        CREATE TABLE IF NOT EXISTS scenarios (
            run_id TEXT NOT NULL,
            lever_key TEXT NOT NULL,
            title TEXT NOT NULL,
            lens TEXT NOT NULL,
            repo_count INTEGER NOT NULL,
            average_expected_lens_delta REAL NOT NULL,
            projected_tier_promotions INTEGER NOT NULL,
            PRIMARY KEY (run_id, lever_key)
        );
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO warehouse_meta (key, value) VALUES (?, ?)",
        ("schema_version", str(WAREHOUSE_SCHEMA_VERSION)),
    )
    _ensure_column(conn, "audit_runs", "report_path", "TEXT")
    _ensure_column(conn, "audit_runs", "security_governance_preview_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "audit_runs", "campaign_summary_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "audit_runs", "writeback_preview_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "audit_runs", "writeback_results_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "audit_runs", "managed_state_drift_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "audit_runs", "rollback_preview_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "audit_runs", "campaign_history_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "audit_runs", "governance_preview_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "audit_runs", "governance_approval_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "audit_runs", "governance_results_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "audit_runs", "governance_history_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "audit_runs", "governance_drift_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "audit_runs", "governance_summary_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "audit_runs", "preflight_summary_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "audit_runs", "baseline_signature", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "audit_runs", "baseline_context_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "audit_runs", "review_summary_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "audit_runs", "review_alerts_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "audit_runs", "material_changes_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "audit_runs", "review_targets_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "audit_runs", "review_history_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "audit_runs", "watch_state_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "audit_runs", "operator_summary_json", "TEXT NOT NULL DEFAULT '{}'")
    _ensure_column(conn, "audit_runs", "operator_queue_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(conn, "action_runs", "lifecycle_state", "TEXT NOT NULL DEFAULT 'planned'")
    _ensure_column(conn, "action_runs", "reconciliation_outcome", "TEXT NOT NULL DEFAULT 'preview'")
    _ensure_column(conn, "action_runs", "closed_at", "TEXT")
    _ensure_column(conn, "action_runs", "closed_reason", "TEXT")
    _ensure_column(conn, "action_runs", "reopened_at", "TEXT")
    _ensure_column(conn, "action_runs", "drift_state", "TEXT")
    _ensure_column(conn, "action_runs", "rollback_state", "TEXT")


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_def: str) -> None:
    existing = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")


def _insert_run(conn: sqlite3.Connection, report: AuditReport, report_path: Path | None) -> None:
    run_id = f"{report.username}:{report.generated_at.isoformat()}"
    conn.execute(
        """
        INSERT OR REPLACE INTO audit_runs (
            run_id, username, generated_at, schema_version, scoring_profile, run_mode, report_path,
            total_repos, repos_audited, average_score, portfolio_baseline_size, baseline_signature, baseline_context_json,
            tier_distribution_json, language_distribution_json, lens_summary_json,
            security_summary_json, security_governance_preview_json, collections_json, scenario_summary_json,
            campaign_summary_json, writeback_preview_json, writeback_results_json,
            managed_state_drift_json, rollback_preview_json, campaign_history_json,
            governance_preview_json, governance_approval_json, governance_results_json,
            governance_history_json, governance_drift_json, governance_summary_json, review_summary_json, review_alerts_json,
            preflight_summary_json, material_changes_json, review_targets_json, review_history_json, watch_state_json,
            operator_summary_json, operator_queue_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            report.username,
            report.generated_at.isoformat(),
            report.schema_version,
            report.scoring_profile,
            report.run_mode,
            str(report_path) if report_path else None,
            report.total_repos,
            report.repos_audited,
            report.average_score,
            report.portfolio_baseline_size,
            report.baseline_signature,
            json.dumps(report.baseline_context),
            json.dumps(report.tier_distribution),
            json.dumps(report.language_distribution),
            json.dumps(report.lenses),
            json.dumps(report.security_posture),
            json.dumps(report.security_governance_preview),
            json.dumps(report.collections),
            json.dumps(report.scenario_summary),
            json.dumps(report.campaign_summary),
            json.dumps(report.writeback_preview),
            json.dumps(report.writeback_results),
            json.dumps(report.managed_state_drift),
            json.dumps(report.rollback_preview),
            json.dumps(report.campaign_history),
            json.dumps(report.governance_preview),
            json.dumps(report.governance_approval),
            json.dumps(report.governance_results),
            json.dumps(report.governance_history),
            json.dumps(report.governance_drift),
            json.dumps(report.governance_summary),
            json.dumps(report.review_summary),
            json.dumps(report.review_alerts),
            json.dumps(report.preflight_summary),
            json.dumps(report.material_changes),
            json.dumps(report.review_targets),
            json.dumps(report.review_history),
            json.dumps(report.watch_state),
            json.dumps(report.operator_summary),
            json.dumps(report.operator_queue),
        ),
    )

    for audit in report.audits:
        repo_id = audit.metadata.full_name
        conn.execute(
            """
            INSERT OR REPLACE INTO repos (
                repo_id, name, full_name, html_url, primary_language, private, fork, archived
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                repo_id,
                audit.metadata.name,
                audit.metadata.full_name,
                audit.metadata.html_url,
                audit.metadata.language,
                int(audit.metadata.private),
                int(audit.metadata.fork),
                int(audit.metadata.archived),
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO repo_snapshots (
                run_id, repo_id, overall_score, interest_score, completeness_tier,
                interest_tier, grade, interest_grade, badges_json, flags_json,
                security_posture_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                repo_id,
                audit.overall_score,
                audit.interest_score,
                audit.completeness_tier,
                audit.interest_tier,
                audit.grade,
                audit.interest_grade,
                json.dumps(audit.badges),
                json.dumps(audit.flags),
                json.dumps(audit.security_posture),
            ),
        )

        for result in audit.analyzer_results:
            conn.execute(
                """
                INSERT OR REPLACE INTO dimension_scores (
                    run_id, repo_id, dimension, score, max_score, findings_json, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    repo_id,
                    result.dimension,
                    result.score,
                    result.max_score,
                    json.dumps(result.findings),
                    json.dumps(result.details),
                ),
            )

        for lens_name, lens_data in audit.lenses.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO lens_scores (
                    run_id, repo_id, lens, score, orientation, summary, drivers_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    repo_id,
                    lens_name,
                    lens_data.get("score", 0.0),
                    lens_data.get("orientation", "higher-is-better"),
                    lens_data.get("summary", ""),
                    json.dumps(lens_data.get("drivers", [])),
                ),
            )

        for hotspot in audit.hotspots:
            conn.execute(
                """
                INSERT OR REPLACE INTO hotspots (
                    run_id, repo_id, category, severity, title, summary, recommended_action
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    repo_id,
                    hotspot.get("category", "unknown"),
                    hotspot.get("severity", 0.0),
                    hotspot.get("title", ""),
                    hotspot.get("summary", ""),
                    hotspot.get("recommended_action", ""),
                ),
            )

        security = audit.security_posture or {}
        conn.execute(
            """
            INSERT OR REPLACE INTO security_posture (
                run_id, repo_id, label, score, secrets_found, dangerous_files_json,
                has_security_md, has_dependabot, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                repo_id,
                security.get("label", "unknown"),
                security.get("score", 0.0),
                security.get("secrets_found", 0),
                json.dumps(security.get("dangerous_files", [])),
                int(security.get("has_security_md", False)),
                int(security.get("has_dependabot", False)),
                json.dumps(security.get("evidence", [])),
            ),
        )

        controls = {
            "security_md": {
                "status": "enabled" if security.get("has_security_md") else "missing",
                "source": "local",
                "details": {"has_security_md": security.get("has_security_md", False)},
            },
            "dependabot_config": {
                "status": "enabled" if security.get("has_dependabot") else "missing",
                "source": "local",
                "details": {"has_dependabot": security.get("has_dependabot", False)},
            },
            "dependency_graph": {
                "status": security.get("github", {}).get("dependency_graph_status", "unavailable"),
                "source": "github",
                "details": {
                    "enabled": security.get("github", {}).get("dependency_graph_enabled"),
                },
            },
            "sbom_export": {
                "status": security.get("github", {}).get("sbom_status", "unavailable"),
                "source": "github",
                "details": {
                    "exportable": security.get("github", {}).get("sbom_exportable"),
                },
            },
            "code_scanning": {
                "status": security.get("github", {}).get("code_scanning_status", "unavailable"),
                "source": "github",
                "details": {
                    "open_alerts": security.get("github", {}).get("code_scanning_alerts"),
                },
            },
            "secret_scanning": {
                "status": security.get("github", {}).get("secret_scanning_status", "unavailable"),
                "source": "github",
                "details": {
                    "open_alerts": security.get("github", {}).get("secret_scanning_alerts"),
                },
            },
        }
        for control_name, control_data in controls.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO security_controls (
                    run_id, repo_id, control_name, status, source, details_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    repo_id,
                    control_name,
                    control_data.get("status", "unknown"),
                    control_data.get("source", "merged"),
                    json.dumps(control_data.get("details", {})),
                ),
            )

        alerts = {
            "code_scanning": {
                "open_count": security.get("github", {}).get("code_scanning_alerts") or 0,
                "source": "github",
                "details": {"status": security.get("github", {}).get("code_scanning_status", "unavailable")},
            },
            "secret_scanning": {
                "open_count": security.get("github", {}).get("secret_scanning_alerts") or 0,
                "source": "github",
                "details": {"status": security.get("github", {}).get("secret_scanning_status", "unavailable")},
            },
        }
        for alert_type, alert_data in alerts.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO security_alerts (
                    run_id, repo_id, alert_type, open_count, source, details_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    repo_id,
                    alert_type,
                    alert_data.get("open_count", 0),
                    alert_data.get("source", "merged"),
                    json.dumps(alert_data.get("details", {})),
                ),
            )

        for provider_name, provider_data in (security.get("providers") or {}).items():
            details = security.get(provider_name, {}) if provider_name in {"local", "github", "scorecard"} else {}
            conn.execute(
                """
                INSERT OR REPLACE INTO security_providers (
                    run_id, repo_id, provider_name, available, score, details_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    repo_id,
                    provider_name,
                    int(bool(provider_data.get("available"))),
                    provider_data.get("score"),
                    json.dumps(details),
                ),
            )

        for recommendation in security.get("recommendations", []):
            conn.execute(
                """
                INSERT OR REPLACE INTO security_recommendations (
                    run_id, repo_id, recommendation_key, title, priority, effort,
                    source, expected_posture_lift, why
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    repo_id,
                    recommendation.get("key", recommendation.get("title", "")),
                    recommendation.get("title", ""),
                    recommendation.get("priority", "medium"),
                    recommendation.get("effort", ""),
                    recommendation.get("source", "merged"),
                    recommendation.get("expected_posture_lift", 0.0),
                    recommendation.get("why", ""),
                ),
            )

        dep_result = next((result for result in audit.analyzer_results if result.dimension == "dependencies"), None)
        dep_details = dep_result.details if dep_result else {}
        manifest_files = dep_details.get("manifest_files", []) or dep_details.get("manifests", [])
        dependency_count = dep_details.get("total_dependencies", dep_details.get("manifest_count", 0)) or 0
        libyears = dep_details.get("total_libyears", 0.0) or 0.0
        conn.execute(
            """
            INSERT OR REPLACE INTO dependency_inventory (
                run_id, repo_id, manifest_files_json, dependency_count, libyears, details_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                repo_id,
                json.dumps(manifest_files),
                dependency_count,
                libyears,
                json.dumps(dep_details),
            ),
        )

        for action in audit.action_candidates:
            conn.execute(
                """
                INSERT OR REPLACE INTO actions (
                    run_id, repo_id, action_key, title, lens, effort, confidence,
                    expected_lens_delta, expected_tier_movement, rationale, action_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    repo_id,
                    action.get("key", action.get("title", "")),
                    action.get("title", ""),
                    action.get("lens", ""),
                    action.get("effort", ""),
                    action.get("confidence", 0.0),
                    action.get("expected_lens_delta", 0.0),
                    action.get("expected_tier_movement", ""),
                    action.get("rationale", ""),
                    action.get("action", ""),
                ),
            )

    for profile_name, profile_data in report.profiles.items():
        conn.execute(
            """
            INSERT OR REPLACE INTO profiles (
                run_id, profile_name, description, lens_weights_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                run_id,
                profile_name,
                profile_data.get("description", ""),
                json.dumps(profile_data.get("lens_weights", {})),
            ),
        )

    for collection_name, collection_data in report.collections.items():
        repos = collection_data.get("repos", [])
        for rank_index, repo_data in enumerate(repos, start=1):
            repo_name = repo_data["name"] if isinstance(repo_data, dict) else str(repo_data)
            reason = repo_data.get("reason", "") if isinstance(repo_data, dict) else ""
            conn.execute(
                """
                INSERT OR REPLACE INTO collections (
                    run_id, collection_name, repo_name, rank_index, reason, description
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    collection_name,
                    repo_name,
                    rank_index,
                    reason,
                    collection_data.get("description", ""),
                ),
            )

    for lever in report.scenario_summary.get("top_levers", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO scenarios (
                run_id, lever_key, title, lens, repo_count,
                average_expected_lens_delta, projected_tier_promotions
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                lever.get("key", lever.get("title", "")),
                lever.get("title", ""),
                lever.get("lens", ""),
                lever.get("repo_count", 0),
                lever.get("average_expected_lens_delta", 0.0),
                lever.get("projected_tier_promotions", 0),
            ),
        )

    if report.campaign_summary:
        campaign_run = report.writeback_results.get("campaign_run", {}) if isinstance(report.writeback_results, dict) else {}
        conn.execute(
            """
            INSERT OR REPLACE INTO campaign_runs (
                run_id, campaign_type, label, portfolio_profile, collection_name,
                writeback_target, mode, generated_at, generated_action_ids_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                report.campaign_summary.get("campaign_type", ""),
                report.campaign_summary.get("label", ""),
                campaign_run.get("portfolio_profile", report.campaign_summary.get("portfolio_profile", "default")),
                campaign_run.get("collection_name"),
                campaign_run.get("writeback_target", report.writeback_results.get("target", "preview-only")),
                campaign_run.get("mode", report.writeback_results.get("mode", "preview")),
                campaign_run.get("generated_at", report.generated_at.isoformat()),
                json.dumps(campaign_run.get("generated_action_ids", [])),
            ),
        )

    for action_run in report.action_runs:
        conn.execute(
            """
            INSERT OR REPLACE INTO action_runs (
                run_id, action_id, repo_id, campaign_type, target, status,
                lifecycle_state, reconciliation_outcome, closed_at, closed_reason,
                reopened_at, drift_state, rollback_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                action_run.get("action_id", ""),
                action_run.get("repo_full_name", ""),
                action_run.get("campaign_type", ""),
                action_run.get("target", "preview-only"),
                action_run.get("status", "preview"),
                action_run.get("lifecycle_state", "planned"),
                action_run.get("reconciliation_outcome", action_run.get("status", "preview")),
                action_run.get("closed_at"),
                action_run.get("closed_reason"),
                action_run.get("reopened_at"),
                action_run.get("drift_state"),
                action_run.get("rollback_state"),
            ),
        )

    for history_entry in report.campaign_history:
        conn.execute(
            """
            INSERT OR REPLACE INTO campaign_history (
                run_id, action_id, repo_id, campaign_type, lifecycle_state,
                reconciliation_outcome, closed_at, closed_reason, reopened_at,
                supersedes_action_id, superseded_by_action_id, drift_state,
                rollback_state, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                history_entry.get("action_id", ""),
                history_entry.get("repo_full_name", ""),
                history_entry.get("campaign_type", ""),
                history_entry.get("lifecycle_state", "planned"),
                history_entry.get("reconciliation_outcome", "preview"),
                history_entry.get("closed_at"),
                history_entry.get("closed_reason"),
                history_entry.get("reopened_at"),
                history_entry.get("supersedes_action_id"),
                history_entry.get("superseded_by_action_id"),
                history_entry.get("drift_state"),
                history_entry.get("rollback_state"),
                json.dumps(history_entry),
            ),
        )

    for drift in report.managed_state_drift:
        conn.execute(
            """
            INSERT OR REPLACE INTO campaign_drift_events (
                run_id, action_id, repo_id, campaign_type, target, drift_state, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                drift.get("action_id", ""),
                drift.get("repo_full_name", ""),
                drift.get("campaign_type", report.campaign_summary.get("campaign_type", "")),
                drift.get("target", ""),
                drift.get("drift_state", drift.get("drift_type", "drifted")),
                json.dumps(drift),
            ),
        )

    for item in report.rollback_preview.get("items", []) if isinstance(report.rollback_preview, dict) else []:
        conn.execute(
            """
            INSERT OR REPLACE INTO rollback_runs (
                run_id, source_run_id, preview_json, results_json, status
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                f"{run_id}:{item.get('action_id', item.get('repo_full_name', 'rollback'))}:{item.get('target', '')}",
                run_id,
                json.dumps(item),
                "{}",
                item.get("rollback_state", "preview"),
            ),
        )

    for result in report.writeback_results.get("results", []) if isinstance(report.writeback_results, dict) else []:
        target = result.get("target", "")
        if target.startswith("github"):
            conn.execute(
                """
                INSERT OR REPLACE INTO github_writebacks (
                    run_id, repo_id, target, status, before_json, after_json, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    result.get("repo_full_name", ""),
                    target,
                    result.get("status", "unknown"),
                    json.dumps(result.get("before", {})),
                    json.dumps(result.get("after", {})),
                    json.dumps(result),
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO campaign_target_snapshots (
                    run_id, action_id, repo_id, target, status, external_key,
                    before_json, after_json, expected_json, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    result.get("action_id", ""),
                    result.get("repo_full_name", ""),
                    target,
                    result.get("status", "unknown"),
                    str(result.get("number") or result.get("url") or ""),
                    json.dumps(result.get("before", {})),
                    json.dumps(result.get("after", {})),
                    json.dumps(result.get("expected", {})),
                    json.dumps(result),
                ),
            )
        elif target.startswith("notion"):
            conn.execute(
                """
                INSERT OR REPLACE INTO notion_writebacks (
                    run_id, action_id, status, details_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    run_id,
                    result.get("action_id", ""),
                    result.get("status", "unknown"),
                    json.dumps(result),
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO campaign_target_snapshots (
                    run_id, action_id, repo_id, target, status, external_key,
                    before_json, after_json, expected_json, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    result.get("action_id", ""),
                    result.get("repo_full_name", ""),
                    target,
                    result.get("status", "unknown"),
                    str(result.get("page_id") or result.get("url") or ""),
                    json.dumps(result.get("before", {})),
                    json.dumps(result.get("after", {})),
                    json.dumps(result.get("expected", {})),
                    json.dumps(result),
                ),
            )

    for action_id, refs in report.external_refs.items():
        for ref_key, ref_value in refs.items():
            conn.execute(
                """
                INSERT OR REPLACE INTO external_refs (
                    run_id, action_id, ref_key, ref_value
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    run_id,
                    action_id,
                    ref_key,
                    str(ref_value),
                ),
            )

    if report.governance_approval:
        conn.execute(
            """
            INSERT OR REPLACE INTO governance_approvals (
                source_run_id, approved_at, scope, fingerprint, action_count,
                applyable_count, status, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.governance_approval.get("source_run_id", ""),
                report.governance_approval.get("approved_at", report.generated_at.isoformat()),
                report.governance_approval.get("scope", "all"),
                report.governance_approval.get("fingerprint", ""),
                report.governance_approval.get("action_count", 0),
                report.governance_approval.get("applyable_count", 0),
                report.governance_approval.get("status", "approved"),
                json.dumps(report.governance_approval),
            ),
        )

    if report.governance_results:
        governance_run_id = f"governance:{run_id}"
        conn.execute(
            """
            INSERT OR REPLACE INTO governance_runs (
                run_id, source_run_id, scope, fingerprint, status, summary_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                governance_run_id,
                report.governance_results.get("source_run_id", ""),
                report.governance_results.get("scope", report.governance_approval.get("scope", "all") if isinstance(report.governance_approval, dict) else "all"),
                report.governance_results.get("fingerprint", ""),
                report.governance_results.get("mode", "apply"),
                json.dumps(report.governance_results),
            ),
        )
        for result in report.governance_results.get("results", []):
            conn.execute(
                """
                INSERT OR REPLACE INTO governance_action_results (
                    run_id, action_id, repo_id, control_key, status, rollback_state,
                    before_json, after_json, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    governance_run_id,
                    result.get("action_id", ""),
                    result.get("repo_full_name", ""),
                    result.get("control_key", ""),
                    result.get("status", "unknown"),
                    result.get("rollback_state", "rollback-available" if result.get("rollback_available") else "non-reversible"),
                    json.dumps(result.get("before", {})),
                    json.dumps(result.get("after", {})),
                    json.dumps(result),
                ),
            )

    for drift in report.governance_drift:
        conn.execute(
            """
            INSERT OR REPLACE INTO governance_drift_events (
                run_id, action_id, repo_id, control_key, drift_type, details_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"governance:{run_id}",
                drift.get("action_id"),
                drift.get("repo_full_name", drift.get("repo", "")),
                drift.get("control_key", drift.get("target")),
                drift.get("drift_type", "drifted"),
                json.dumps(drift),
            ),
        )


def _row_dict(cursor: sqlite3.Cursor, row: sqlite3.Row) -> dict:
    return {description[0]: row[index] for index, description in enumerate(cursor.description)}


def _connect(output_dir: Path) -> sqlite3.Connection | None:
    db_path = output_dir / WAREHOUSE_FILENAME
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_audit_report_path(output_dir: Path, run_id: str) -> Path | None:
    conn = _connect(output_dir)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT report_path FROM audit_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["report_path"]:
        return None
    return Path(row["report_path"])


def load_campaign_run(output_dir: Path, run_id: str) -> dict | None:
    conn = _connect(output_dir)
    if conn is None:
        return None
    try:
        row = conn.execute(
            """
            SELECT run_id, campaign_type, label, portfolio_profile, collection_name,
                   writeback_target, mode, generated_at, generated_action_ids_json
            FROM campaign_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if not row:
            return None
        action_rows = conn.execute(
            """
            SELECT action_id, repo_id, campaign_type, target, status, lifecycle_state,
                   reconciliation_outcome, closed_at, closed_reason, reopened_at,
                   drift_state, rollback_state
            FROM action_runs
            WHERE run_id = ?
            ORDER BY repo_id, action_id
            """,
            (run_id,),
        ).fetchall()
    finally:
        conn.close()
    return {
        "run_id": row["run_id"],
        "campaign_type": row["campaign_type"],
        "label": row["label"],
        "portfolio_profile": row["portfolio_profile"],
        "collection_name": row["collection_name"],
        "writeback_target": row["writeback_target"],
        "mode": row["mode"],
        "generated_at": row["generated_at"],
        "generated_action_ids": json.loads(row["generated_action_ids_json"] or "[]"),
        "action_runs": [dict(item) for item in action_rows],
    }


def load_governance_approval(output_dir: Path, source_run_id: str) -> dict | None:
    conn = _connect(output_dir)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT details_json FROM governance_approvals WHERE source_run_id = ?",
            (source_run_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return json.loads(row["details_json"] or "{}")


def load_governance_history(output_dir: Path, *, source_run_id: str, limit: int = 10) -> list[dict]:
    conn = _connect(output_dir)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT summary_json
            FROM governance_runs
            WHERE source_run_id = ?
            ORDER BY run_id DESC
            LIMIT ?
            """,
            (source_run_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [json.loads(row["summary_json"] or "{}") for row in rows]


def load_campaign_history(output_dir: Path, campaign_type: str, limit: int = 30) -> list[dict]:
    conn = _connect(output_dir)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT campaign_history.details_json
            FROM campaign_history
            JOIN audit_runs ON audit_runs.run_id = campaign_history.run_id
            WHERE campaign_history.campaign_type = ?
            ORDER BY audit_runs.generated_at DESC, campaign_history.repo_id, campaign_history.action_id
            LIMIT ?
            """,
            (campaign_type, limit),
        ).fetchall()
    finally:
        conn.close()
    return [json.loads(row["details_json"] or "{}") for row in rows]


def load_latest_campaign_state(output_dir: Path, campaign_type: str) -> dict:
    conn = _connect(output_dir)
    if conn is None:
        return {"campaign_type": campaign_type, "actions": {}, "run_id": None}
    try:
        run_row = conn.execute(
            """
            SELECT campaign_runs.run_id
            FROM campaign_runs
            JOIN audit_runs ON audit_runs.run_id = campaign_runs.run_id
            WHERE campaign_runs.campaign_type = ?
            ORDER BY audit_runs.generated_at DESC
            LIMIT 1
            """,
            (campaign_type,),
        ).fetchone()
        if not run_row:
            return {"campaign_type": campaign_type, "actions": {}, "run_id": None}
        run_id = run_row["run_id"]
        history_rows = conn.execute(
            """
            SELECT action_id, repo_id, lifecycle_state, reconciliation_outcome, closed_at,
                   closed_reason, reopened_at, supersedes_action_id, superseded_by_action_id,
                   drift_state, rollback_state, details_json
            FROM campaign_history
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()
        if not history_rows:
            history_rows = conn.execute(
                """
                SELECT action_id, repo_id, lifecycle_state, reconciliation_outcome, closed_at,
                       closed_reason, reopened_at, NULL AS supersedes_action_id,
                       NULL AS superseded_by_action_id, drift_state, rollback_state,
                       '{}' AS details_json
                FROM action_runs
                WHERE run_id = ? AND campaign_type = ?
                """,
                (run_id, campaign_type),
            ).fetchall()
        snapshot_rows = conn.execute(
            """
            SELECT action_id, target, status, external_key, before_json, after_json, expected_json, details_json
            FROM campaign_target_snapshots
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()
        ref_rows = conn.execute(
            """
            SELECT action_id, ref_key, ref_value
            FROM external_refs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()
    finally:
        conn.close()

    actions: dict[str, dict] = {}
    for row in history_rows:
        details = json.loads(row["details_json"] or "{}")
        actions[row["action_id"]] = {
            "action_id": row["action_id"],
            "repo_full_name": row["repo_id"],
            "campaign_type": campaign_type,
            "lifecycle_state": row["lifecycle_state"],
            "reconciliation_outcome": row["reconciliation_outcome"],
            "closed_at": row["closed_at"],
            "closed_reason": row["closed_reason"],
            "reopened_at": row["reopened_at"],
            "supersedes_action_id": row["supersedes_action_id"],
            "superseded_by_action_id": row["superseded_by_action_id"],
            "drift_state": row["drift_state"],
            "rollback_state": row["rollback_state"],
            "details": details,
            "snapshots": {},
            "external_refs": {},
        }
    for row in snapshot_rows:
        action = actions.setdefault(
            row["action_id"],
            {
                "action_id": row["action_id"],
                "repo_full_name": "",
                "campaign_type": campaign_type,
                "lifecycle_state": "planned",
                "reconciliation_outcome": "preview",
                "snapshots": {},
                "external_refs": {},
            },
        )
        action["snapshots"][row["target"]] = {
            "status": row["status"],
            "external_key": row["external_key"],
            "before": json.loads(row["before_json"] or "{}"),
            "after": json.loads(row["after_json"] or "{}"),
            "expected": json.loads(row["expected_json"] or "{}"),
            "details": json.loads(row["details_json"] or "{}"),
        }
    for row in ref_rows:
        action = actions.setdefault(
            row["action_id"],
            {
                "action_id": row["action_id"],
                "repo_full_name": "",
                "campaign_type": campaign_type,
                "lifecycle_state": "planned",
                "reconciliation_outcome": "preview",
                "snapshots": {},
                "external_refs": {},
            },
        )
        action["external_refs"][row["ref_key"]] = row["ref_value"]
    return {"campaign_type": campaign_type, "actions": actions, "run_id": run_id}


def load_latest_audit_runs(output_dir: Path, username: str, limit: int = 20) -> list[dict]:
    conn = _connect(output_dir)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT run_id, username, generated_at, run_mode, scoring_profile,
                   portfolio_baseline_size, baseline_signature, baseline_context_json, report_path, preflight_summary_json,
                   governance_summary_json,
                   review_summary_json, operator_summary_json
            FROM audit_runs
            WHERE username = ?
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (username, limit),
        ).fetchall()
    finally:
        conn.close()
    results: list[dict] = []
    for row in rows:
        results.append(
            {
                "run_id": row["run_id"],
                "username": row["username"],
                "generated_at": row["generated_at"],
                "run_mode": row["run_mode"],
                "scoring_profile": row["scoring_profile"],
                "portfolio_baseline_size": row["portfolio_baseline_size"],
                "baseline_signature": row["baseline_signature"],
                "baseline_context": json.loads(row["baseline_context_json"] or "{}"),
                "report_path": row["report_path"],
                "preflight_summary": json.loads(row["preflight_summary_json"] or "{}"),
                "governance_summary": json.loads(row["governance_summary_json"] or "{}"),
                "review_summary": json.loads(row["review_summary_json"] or "{}"),
                "operator_summary": json.loads(row["operator_summary_json"] or "{}"),
            }
        )
    return results


def load_review_history(output_dir: Path, username: str, limit: int = 10) -> list[dict]:
    conn = _connect(output_dir)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT review_summary_json
            FROM audit_runs
            WHERE username = ?
              AND review_summary_json IS NOT NULL
              AND review_summary_json != '{}'
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (username, limit),
        ).fetchall()
    finally:
        conn.close()
    history: list[dict] = []
    for row in rows:
        item = json.loads(row["review_summary_json"] or "{}")
        if item:
            history.append(item)
    return history


def load_watch_checkpoint(output_dir: Path, username: str) -> dict | None:
    conn = _connect(output_dir)
    if conn is None:
        return None
    try:
        row = conn.execute(
            """
            SELECT watch_state_json
            FROM audit_runs
            WHERE username = ?
              AND watch_state_json IS NOT NULL
              AND watch_state_json != '{}'
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            (username,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    state = json.loads(row["watch_state_json"] or "{}")
    return state or None


def load_latest_operator_state(output_dir: Path, username: str) -> dict | None:
    conn = _connect(output_dir)
    if conn is None:
        return None
    try:
        row = conn.execute(
            """
            SELECT run_id, generated_at, report_path, preflight_summary_json,
                   baseline_signature, baseline_context_json,
                   governance_summary_json,
                   review_summary_json, review_alerts_json, material_changes_json,
                   review_targets_json, review_history_json, watch_state_json,
                   operator_summary_json, operator_queue_json
            FROM audit_runs
            WHERE username = ?
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            (username,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "run_id": row["run_id"],
        "generated_at": row["generated_at"],
        "report_path": row["report_path"],
        "baseline_signature": row["baseline_signature"],
        "baseline_context": json.loads(row["baseline_context_json"] or "{}"),
        "preflight_summary": json.loads(row["preflight_summary_json"] or "{}"),
        "governance_summary": json.loads(row["governance_summary_json"] or "{}"),
        "review_summary": json.loads(row["review_summary_json"] or "{}"),
        "review_alerts": json.loads(row["review_alerts_json"] or "[]"),
        "material_changes": json.loads(row["material_changes_json"] or "[]"),
        "review_targets": json.loads(row["review_targets_json"] or "[]"),
        "review_history": json.loads(row["review_history_json"] or "[]"),
        "watch_state": json.loads(row["watch_state_json"] or "{}"),
        "operator_summary": json.loads(row["operator_summary_json"] or "{}"),
        "operator_queue": json.loads(row["operator_queue_json"] or "[]"),
    }


def load_recent_operator_changes(output_dir: Path, username: str, limit: int = 20) -> list[dict]:
    conn = _connect(output_dir)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT details_json AS payload, 'campaign' AS kind, audit_runs.generated_at
            FROM campaign_history
            JOIN audit_runs ON audit_runs.run_id = campaign_history.run_id
            WHERE audit_runs.username = ?
              AND campaign_history.reconciliation_outcome IN ('closed', 'reopened', 'drifted')
            UNION ALL
            SELECT details_json AS payload, 'governance' AS kind, audit_runs.generated_at
            FROM governance_drift_events
            JOIN audit_runs ON audit_runs.run_id = REPLACE(governance_drift_events.run_id, 'governance:', '')
            WHERE audit_runs.username = ?
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (username, username, limit),
        ).fetchall()
    finally:
        conn.close()
    changes: list[dict] = []
    for row in rows:
        payload = json.loads(row["payload"] or "{}")
        payload["kind"] = row["kind"]
        payload["generated_at"] = row["generated_at"]
        changes.append(payload)
    return changes


def load_operator_state_history(output_dir: Path, username: str, limit: int = 5) -> list[dict]:
    conn = _connect(output_dir)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT run_id, generated_at, operator_summary_json, operator_queue_json
            FROM audit_runs
            WHERE username = ?
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (username, limit),
        ).fetchall()
    finally:
        conn.close()
    history: list[dict] = []
    for row in rows:
        history.append(
            {
                "run_id": row["run_id"],
                "generated_at": row["generated_at"],
                "operator_summary": json.loads(row["operator_summary_json"] or "{}"),
                "operator_queue": json.loads(row["operator_queue_json"] or "[]"),
            }
        )
    return history


def load_operator_calibration_history(output_dir: Path, username: str, limit: int = 20) -> list[dict]:
    conn = _connect(output_dir)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            """
            SELECT run_id, generated_at, operator_summary_json, operator_queue_json
            FROM audit_runs
            WHERE username = ?
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (username, limit),
        ).fetchall()
    finally:
        conn.close()
    history: list[dict] = []
    for row in rows:
        history.append(
            {
                "run_id": row["run_id"],
                "generated_at": row["generated_at"],
                "operator_summary": json.loads(row["operator_summary_json"] or "{}"),
                "operator_queue": json.loads(row["operator_queue_json"] or "[]"),
            }
        )
    return history


def load_recent_operator_evidence(
    output_dir: Path,
    username: str,
    *,
    snapshot_limit: int = 10,
    event_limit: int = 30,
) -> dict:
    conn = _connect(output_dir)
    if conn is None:
        return {"history": [], "events": []}
    try:
        snapshot_rows = conn.execute(
            """
            SELECT run_id, generated_at, operator_summary_json, operator_queue_json
            FROM audit_runs
            WHERE username = ?
            ORDER BY generated_at DESC
            LIMIT ?
            """,
            (username, snapshot_limit),
        ).fetchall()
        event_rows = conn.execute(
            """
            SELECT audit_runs.generated_at AS recorded_at,
                   'campaign' AS source,
                   campaign_history.action_id AS action_id,
                   campaign_history.repo_id AS repo_id,
                   campaign_history.campaign_type AS event_group,
                   campaign_history.lifecycle_state AS event_type,
                   campaign_history.reconciliation_outcome AS outcome,
                   campaign_history.closed_reason AS closed_reason,
                   campaign_history.reopened_at AS reopened_at,
                   campaign_history.details_json AS details_json
            FROM campaign_history
            JOIN audit_runs ON audit_runs.run_id = campaign_history.run_id
            WHERE audit_runs.username = ?
            UNION ALL
            SELECT audit_runs.generated_at AS recorded_at,
                   'governance' AS source,
                   governance_drift_events.action_id AS action_id,
                   governance_drift_events.repo_id AS repo_id,
                   governance_drift_events.control_key AS event_group,
                   governance_drift_events.drift_type AS event_type,
                   'drifted' AS outcome,
                   '' AS closed_reason,
                   '' AS reopened_at,
                   governance_drift_events.details_json AS details_json
            FROM governance_drift_events
            JOIN audit_runs ON audit_runs.run_id = REPLACE(governance_drift_events.run_id, 'governance:', '')
            WHERE audit_runs.username = ?
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            (username, username, event_limit),
        ).fetchall()
    finally:
        conn.close()
    return {
        "history": [
            {
                "run_id": row["run_id"],
                "generated_at": row["generated_at"],
                "operator_summary": json.loads(row["operator_summary_json"] or "{}"),
                "operator_queue": json.loads(row["operator_queue_json"] or "[]"),
            }
            for row in snapshot_rows
        ],
        "events": [_normalize_operator_evidence_event(row) for row in event_rows],
    }


def _normalize_operator_evidence_event(row: sqlite3.Row) -> dict:
    details = json.loads(row["details_json"] or "{}")
    repo_full_name = details.get("repo_full_name") or row["repo_id"] or ""
    repo = details.get("repo") or (repo_full_name.split("/")[-1] if repo_full_name else "")
    action_id = row["action_id"] or details.get("action_id", "")
    target = details.get("target") or details.get("control_key") or row["event_group"] or ""
    source = row["source"]
    if source == "campaign" and action_id:
        item_id = f"campaign-drift:{action_id}:{target}" if target else f"campaign-drift:{action_id}"
        title = details.get("title") or f"{repo or 'Campaign'} drift needs review"
    elif source == "governance":
        governance_key = action_id or repo_full_name or repo or "governance"
        item_id = f"governance-drift:{governance_key}:{target}" if target else f"governance-drift:{governance_key}"
        title = details.get("title") or f"{repo or 'Governance'} drift needs review"
    else:
        title = details.get("title") or (f"{repo}: {row['event_type']}" if repo else row["event_type"])
        item_id = details.get("item_id") or f"{repo}:{title}".strip(":")
    summary = (
        details.get("summary")
        or details.get("drift_state")
        or details.get("drift_type")
        or details.get("why")
        or row["event_type"]
        or "operator-event"
    )
    outcome = row["outcome"] or row["event_type"] or "recorded"
    if row["reopened_at"]:
        outcome = "reopened"
    elif row["closed_reason"]:
        outcome = row["closed_reason"] or outcome
    return {
        "item_id": item_id,
        "repo": repo,
        "repo_full_name": repo_full_name,
        "title": title,
        "summary": summary,
        "source": source,
        "event_type": row["event_type"] or "recorded",
        "event_group": row["event_group"] or "",
        "outcome": outcome,
        "recorded_at": row["recorded_at"],
    }
