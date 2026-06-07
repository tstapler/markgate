# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-07

### Added
- `docspan push` — push local markdown files to Google Docs or Confluence
- `docspan pull` — pull remote documents into local markdown files with three-way merge
- `docspan status` — show current mapping status in a table
- `docspan auth setup` — interactive authentication setup for `google_docs` and `confluence` backends
- `docspan conflicts list` — list files with unresolved merge conflicts
- `docspan conflicts resolve` — resolve merge conflicts with `remote`, `local`, or `merged` strategy
- Google Docs backend: push and pull via Google Docs API (service account auth)
- Confluence backend: push and pull via Atlassian REST API (API token auth)
- Three-way merge for bidirectional sync conflict detection
- Confluence comment sidecar: pull writes inline and footer comments to `{file}.comments.md`
- `markgate.yaml` config file format with per-mapping direction control (`push`/`pull`/`both`)
- Sync state tracking via `.markgate-state.json` and content-addressed base store in `.markgate-base/`

### Known Limitations
- Google Docs: comments on edited paragraphs are destroyed on push (paragraph-level diff; comments on unchanged paragraphs are preserved)
- Push: no image support — local image files cannot be pushed to Google Docs or Confluence
- Push: no table support — markdown tables are not rendered in Google Docs
- Confluence: requires an Atlassian API token; no OAuth flow
- Confluence: comment sidecar (`{file}.comments.md`) is informational only; comments cannot be pushed back
- Config file is named `markgate.yaml` (not `docspan.yaml`) and state file is `.markgate-state.json` (not `.docspan-state.json`). These will be renamed in v0.2.0.

[Unreleased]: https://github.com/tstapler/docspan/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tstapler/docspan/releases/tag/v0.1.0
