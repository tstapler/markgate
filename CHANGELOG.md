# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0](https://github.com/tstapler/docspan/compare/docspan-v0.1.0...docspan-v0.2.0) (2026-06-09)


### Features

* Add Railway Volume support for persistent state storage ([3a4b76e](https://github.com/tstapler/docspan/commit/3a4b76eb0cbc14afa02f3aa3de2c4607808fad9f))
* Add retry mechanism and improved error handling for Google Drive API ([e8a7b5f](https://github.com/tstapler/docspan/commit/e8a7b5f177ad2c3b8a356852eceb827326f8ce76))
* Auto-reload Google Sheet mappings on each sync cycle ([a2647c6](https://github.com/tstapler/docspan/commit/a2647c6c1435eb5624a389a4e673a57ead012123))
* **confluence:** port adf/markdown/services from markdown-confluence ([e9d1a85](https://github.com/tstapler/docspan/commit/e9d1a85a9747ac75a6d95d6351d18483297726a4))
* scaffold markgate package from google-docs-obsidian-sync fork ([44dd3c5](https://github.com/tstapler/docspan/commit/44dd3c586a670b4689154b2db9bc6cb8673d9702))
* **sync:** Google Docs structural-diff push, Confluence comments, three-way merge ([9a20e34](https://github.com/tstapler/docspan/commit/9a20e3452f2d92a240128d7c8e2f9c4b63a547f9))


### Bug Fixes

* **ci:** add __future__ annotations for Python 3.9 compat in test ([9ceca65](https://github.com/tstapler/docspan/commit/9ceca65ca5ad2040c1c2ec215fc097b02ba1a0c4))
* **ci:** apply ruff autofix across all src and test files ([bee2784](https://github.com/tstapler/docspan/commit/bee2784b940d872045ce33faf0ce53f65150d80d))
* **ci:** resolve ruff lint failures and enable Actions PR creation ([8727e7b](https://github.com/tstapler/docspan/commit/8727e7bcabf1ddec4b4116b06e605ff24d0eaffe))
* Improve nested list indentation in Google Docs to Markdown conversion ([d6a7539](https://github.com/tstapler/docspan/commit/d6a7539d4beade3426e5d0db838f1d9974f7294b))
* Remove CONFIG_YAML dependency, prefer individual env vars ([d5d5d4a](https://github.com/tstapler/docspan/commit/d5d5d4ae25a7c1d7a213071f968eba56a9289da3))
* Resolve service account storage quota error by storing sync state locally ([00e9cb6](https://github.com/tstapler/docspan/commit/00e9cb65033dfb6cca8e0aae2258cde458cfb342))

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
