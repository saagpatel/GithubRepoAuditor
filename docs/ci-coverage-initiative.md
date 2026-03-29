# CI Coverage Initiative — 2026-03-29

## Summary

Added GitHub Actions CI workflows to **18 of 29** repos that had zero CI/CD.
One additional repo (personal-ops) already had CI but was falsely flagged.
All 12 Swift repos previously under-scored on testing (0.3) now score 1.0 after
an analyzer fix that made `*Tests.swift` files visible.

## Repos with CI added

| Repo | Language | Workflow type |
|------|----------|---------------|
| GPT_RAG | Python | pip + pytest |
| RedditSentimentAnalyzer | Python | pip + pytest |
| JSMTicketAnalyticsExport | Python | pip + pytest |
| NetworkMapper | Python | pip + pytest (backend/) |
| SnippetLibrary | Swift/SPM | swift test |
| GhostRoutes | Swift/XcodeGen | xcodegen + xcodebuild test |
| Terroir | Swift/Xcode | xcodebuild test |
| Calibrate | Swift/Xcode | xcodebuild build |
| Cartograph | Swift/XcodeGen | xcodegen + xcodebuild build |
| Chromafield | Swift/Xcode | xcodebuild build |
| Conductor | Swift/Xcode | xcodebuild build |
| Liminal | Swift/Xcode | xcodebuild build |
| Nocturne | Swift/XcodeGen | xcodegen + xcodebuild build |
| Redact | Swift/XcodeGen | xcodegen + xcodebuild build |
| RoomTone | Swift/XcodeGen | xcodegen + xcodebuild build |
| seismoscope | Swift/Xcode | xcodebuild build |
| TideEngine | Swift/Xcode | xcodebuild build |
| Wavelength | Swift/XcodeGen | xcodegen + xcodebuild build |

## Skeleton repos — explicitly out of scope

These 10 repos were audited and intentionally skipped. They have more fundamental
gaps (missing README, minimal or placeholder code) where CI is not the priority.
Re-evaluate if any graduate to wip or functional tier.

| Repo | Language |
|------|----------|
| Afterimage | Swift |
| app | Swift |
| job-search-2026 | Unknown |
| LifeCadenceLedger | TypeScript |
| PageDiffBookmark | JavaScript |
| PhantomFrequencies | GDScript |
| portfolio-actuation-sandbox | Unknown |
| Recall | GDScript |
| SignalDecay | GDScript |
| SynthWave | Unknown |

## Analyzer bugs fixed (PR #15)

Three bugs discovered during this work and fixed in `fix/analyzer-bugs`:

1. **`src/analyzers/testing.py`** — `*Tests.swift` / `*Test.swift` missing from
   `TEST_PATTERNS`. XCTest file count was always 0, capping Swift repos at 0.7.
   After fix: all 12 affected repos jumped to testing score 1.0, revealing
   101 previously invisible test files across the portfolio.

2. **`src/analyzers/cicd.py`** — `Package.swift`, `Podfile`, `project.yml`/`project.yaml`
   not in `_has_build_scripts()`. XcodeGen repos had no build score.

3. **`src/cloner.py`** — hardcoded `/tmp/audit-repos` shared across sessions.
   Replaced with `tempfile.TemporaryDirectory` — each session gets an isolated dir,
   eliminating cross-run collisions on batch audits.
