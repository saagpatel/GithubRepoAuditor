from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.models import AuditReport

WAREHOUSE_FILENAME = "portfolio-warehouse.db"
WAREHOUSE_SCHEMA_VERSION = 3


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
            tier_distribution_json TEXT NOT NULL,
            language_distribution_json TEXT NOT NULL,
            lens_summary_json TEXT NOT NULL,
            security_summary_json TEXT NOT NULL,
            security_governance_preview_json TEXT NOT NULL,
            collections_json TEXT NOT NULL,
            scenario_summary_json TEXT NOT NULL,
            campaign_summary_json TEXT NOT NULL DEFAULT '{}',
            writeback_preview_json TEXT NOT NULL DEFAULT '{}',
            writeback_results_json TEXT NOT NULL DEFAULT '{}'
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
            PRIMARY KEY (run_id, action_id, target)
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
            total_repos, repos_audited, average_score, portfolio_baseline_size,
            tier_distribution_json, language_distribution_json, lens_summary_json,
            security_summary_json, security_governance_preview_json, collections_json, scenario_summary_json,
            campaign_summary_json, writeback_preview_json, writeback_results_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                run_id, action_id, repo_id, campaign_type, target, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                action_run.get("action_id", ""),
                action_run.get("repo_full_name", ""),
                action_run.get("campaign_type", ""),
                action_run.get("target", "preview-only"),
                action_run.get("status", "preview"),
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
