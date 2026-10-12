# KNOWN ISSUES — Invoice Processing System Enhancement

Only genuine, currently-true issues. Nothing speculative and nothing
resolved is listed as open.

| # | Issue | Impact | Status / mitigation |
|---|---|---|---|
| K-1 | The project folder is OneDrive-synced; SQLite files can corrupt under concurrent access (baseline risk T-3). The enhancement adds a background writer from Sprint E1. | Low (single user) | Serial worker + short transactions planned at E1 (busy_timeout); advise pausing OneDrive sync while the app or tests run |
| K-2 | The role mechanism (Sprint E4) is session-based and provides **no authentication** — any browser user can switch roles. | None for the single-user localhost app; blocks any multi-user use | Documented as a workflow demonstration, not a security boundary (ARCHITECTURE.md §6) |
| K-3 | When AI extraction is configured, invoice content is sent to the configured Z.ai endpoint for extraction. | Data egress during extraction | Disclosed in README/REQUIREMENTS; TLS + key in header; no other egress exists |
| K-4 | The GLM vision model has no native JSON mode (verified 2026-10-12), so image extraction relies on prompt-based JSON. | Occasional malformed responses on image inputs | Response validator + one re-ask + raw response retention (E2) |
| K-5 | GLM model names are defaults (`glm-4.6`, `glm-4.5v`) pending confirmation against the real account. | Possible model-name error on first live call | Env-overridable; confirmed and recorded at the E2 live smoke |
| K-6 | `DEBUG=True` remains from the v1 baseline until Sprint E1-5; an unhandled exception would render the Werkzeug debug page. | Stack-trace exposure on unexpected errors (localhost only) | Removed at E1 with the logging work; tracked, not silently ignored |
| K-7 | The v1 statuses `extracted`/`saved` remain valid in the schema as a transitional measure until Sprint E5 rewires review/save; the workflow machine already refuses them. | Transitional only | v3 tightening migration planned in E5 |
| K-8 | Restart recovery (Sprint E1) assumes a single running app instance; two concurrent instances on one database are unsupported. | None in the single-user deployment | Documented in ARCHITECTURE.md §4 |
