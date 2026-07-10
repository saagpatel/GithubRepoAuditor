"""Improvement application flow with dry-run and ledger transitions."""

from __future__ import annotations

from pathlib import Path

from src.cache import ResponseCache
from src.cli_output import print_info
from src.github_client import GitHubClient


def _run_apply_improvements_mode(args, parser) -> None:
    from src.repo_improver import (
        apply_metadata_updates,
        apply_readme_updates,
        generate_execution_report,
        load_improvements,
    )

    improvements_file = getattr(args, "improvements_file", None)
    apply_readmes = getattr(args, "apply_readmes", False)
    apply_metadata = getattr(args, "apply_metadata", False)

    # --apply-metadata always needs a file; --apply-readmes can read from ledger instead.
    if apply_metadata and not improvements_file:
        parser.error("--apply-metadata requires --improvements-file")
    if not apply_readmes and not apply_metadata:
        parser.error("--apply-metadata / --apply-readmes requires --improvements-file")

    cache = None if args.no_cache else ResponseCache()
    client = GitHubClient(token=args.token, cache=cache)
    output_dir = Path(args.output_dir)
    dry_run = getattr(args, "dry_run", False)

    # Load file-based updates (may be empty if no file supplied)
    file_updates: list[dict] = []
    if improvements_file:
        file_updates = list(load_improvements(improvements_file).values())

    all_results: list[dict] = []

    if apply_metadata:
        results = apply_metadata_updates(client, args.username, file_updates, dry_run=dry_run)
        all_results.extend(results)
        ok_count = sum(
            1 for r in results for a in r.get("actions", []) if a.get("ok") or a.get("dry_run")
        )
        print_info(f"Metadata updates: {ok_count} actions {'previewed' if dry_run else 'applied'}")

    if apply_readmes:
        # Build the merged update list:
        #   1) file-based packets (if --improvements-file provided)
        #   2) approved ledger packets (if any, de-duplicated by repo name)
        readme_updates: list[dict] = list(file_updates)
        ledger_packets_by_repo: dict[str, object] = {}

        from src.draft_readmes import (
            assemble_readme_from_approved_sections,
            load_approved_drafts,
            load_approved_sectioned_packets,
            mark_draft_applied,
            mark_section_packet_applied,
            record_draft_apply_failure,
        )

        # ── Path A: per-section sub-records (Sprint 8.5) ─────────────────────
        sectioned_packets = load_approved_sectioned_packets(output_dir)
        sectioned_updates_by_repo: dict[str, tuple[str, str]] = {}  # repo → (packet_id, readme)
        for pid, sections in sectioned_packets.items():
            repo_name_sec: str = str((sections[0].get("repo_name") or "") if sections else "")
            if not repo_name_sec:
                continue
            assembled = assemble_readme_from_approved_sections(sections)
            if assembled is None:
                print_info(f"sectioned packet {pid} has no approved sections; skipping")
                continue
            pending = [s for s in sections if s.get("state", "pending") == "pending"]
            if pending:
                print_info(f"sectioned packet {pid} has {len(pending)} pending sections; skipping")
                continue
            sectioned_updates_by_repo[repo_name_sec] = (pid, assembled)

        for repo_name_sec, (pid, assembled_readme) in sectioned_updates_by_repo.items():
            file_names = {(u.get("name") or u.get("repo", "").split("/")[-1]) for u in file_updates}
            if repo_name_sec not in file_names:
                readme_updates.append({"name": repo_name_sec, "readme": assembled_readme})
                if dry_run:
                    char_count = len(assembled_readme)
                    print_info(
                        f"  [dry-run] would push sectioned README to {repo_name_sec}: "
                        f"{char_count} chars"
                    )

        # ── Path B: legacy whole-packet records ───────────────────────────────
        ledger_packets = load_approved_drafts(output_dir, getattr(args, "username", None))
        for pkt in ledger_packets:
            # Convert DraftReadmePacket → shape expected by apply_readme_updates
            # apply_readme_updates expects: {name: str, readme: str}
            # De-duplicate: file-based takes precedence (already present in readme_updates).
            file_names = {(u.get("name") or u.get("repo", "").split("/")[-1]) for u in file_updates}
            if pkt.repo_name not in file_names:
                readme_updates.append({"name": pkt.repo_name, "readme": pkt.proposed_readme})
                ledger_packets_by_repo[pkt.repo_name] = pkt

        if not readme_updates:
            print_info("README updates: 0 repos to apply (no file and no approved ledger packets).")
        else:
            if dry_run:
                # Print per-repo preview lines for ledger-sourced packets so the operator
                # can see what would be pushed.  File-based packets are also covered because
                # apply_readme_updates returns {"dry_run": True} records when dry_run=True.
                for pkt_repo, _pkt in ledger_packets_by_repo.items():
                    upd = next(
                        (
                            u
                            for u in readme_updates
                            if (u.get("name") or u.get("repo", "").split("/")[-1]) == pkt_repo
                        ),
                        None,
                    )
                    if upd is not None:
                        char_count = len(upd.get("readme", ""))
                        print_info(
                            f"  [dry-run] would push README to {pkt_repo}: {char_count} chars"
                        )

            results = apply_readme_updates(client, args.username, readme_updates, dry_run=dry_run)
            all_results.extend(results)

            # State transitions for ledger-sourced packets (live apply only)
            if not dry_run:
                for result in results:
                    repo_name = result.get("repo", "")
                    # Path A: sectioned packets
                    if repo_name in sectioned_updates_by_repo:
                        pid, _assembled = sectioned_updates_by_repo[repo_name]
                        if result.get("ok"):
                            mark_section_packet_applied(pid, output_dir)
                    # Path B: legacy whole-packet records
                    elif repo_name in ledger_packets_by_repo:
                        pkt = ledger_packets_by_repo[repo_name]
                        if result.get("ok"):
                            mark_draft_applied(output_dir, pkt, apply_result=result)  # type: ignore[arg-type]
                        else:
                            error_msg = str(result.get("error") or "unknown error")
                            record_draft_apply_failure(output_dir, pkt, error=error_msg)  # type: ignore[arg-type]

            ok_count = sum(1 for r in results if r.get("ok") or r.get("dry_run"))
            verb = "previewed" if dry_run else "pushed"
            print_info(
                f"README updates: {ok_count} repos {verb}"
                + (
                    f" ({len(ledger_packets_by_repo)} from ledger)"
                    if ledger_packets_by_repo
                    else ""
                )
            )

    report_path = generate_execution_report(all_results, output_dir)
    print_info(f"Execution report: {report_path}")
