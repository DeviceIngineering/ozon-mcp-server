# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/).

Русская версия истории изменений живёт в README.ru.md и в заметках проекта.

## [2.4.3] — 2026-09-04

### Fixed
- Docker build broke again in 2.4.2: `README.md` is excluded by `.dockerignore`, and
  since 2.4.2 that is exactly the file `pyproject.toml` points `readme` at. The CI
  added in 2.4.1 caught it on the first run — which is what it was added for.

## [2.4.2] — 2026-09-04

### Changed
- English README is now the default one; the Russian text moved to `README.ru.md`
  and the language switcher badges follow. The PyPI page and directory listings read
  the default README, so they are English now too.
- `Context budget` and `Design decisions` sections added in all three languages.
- Repository description translated to English with search keywords.

### Added
- `docs/social-preview.png` (1280×640) for link previews.
- `glama.json` declaring the maintainer for the Glama directory.

## [2.4.1] — 2026-09-03

### Fixed
- `docker compose up -d --build`, the first command in the README, failed on
  `pip install .`: `pyproject.toml` references `LICENSE` and the README, and the
  Dockerfile copied neither. Broken since the PyPI packaging landed — the wheel built
  fine, so nothing surfaced it until someone built the image.

### Added
- `.github/workflows/ci.yml`: pytest on Python 3.11 and 3.12, a Docker build, and a
  check that the built image answers `initialize` and returns a non-empty tool list.

## [2.4.0] — 2026-09-03

### Added
- Tool profiles (`ozon_mcp/toolsets.py`, `OZON_TOOLSETS`): a client without tool search
  pays for the whole catalogue on every request. `pricing,ads` keeps 57 tools and 5 425
  tokens instead of 151 and 12 686; `orders` keeps 33 and 2 611. The `core` profile —
  stores, diagnostics, degradations, company — is always on. Disabled profiles are named
  in the `ozon_list_shops` description, and calling a disabled tool answers which profile
  contains it, so the assistant states the reason instead of "this is not possible".

## [2.3.0] — 2026-09-03

### Added
- Response shaping (`ozon_mcp/shaping.py`): `view: compact | full` presets for the seven
  heaviest tools, a truncation signal when exactly `limit` records come back, and a size
  guard that cuts server-side instead of letting the client truncate silently.
- `search` and `depth` for `ozon_category_tree` — the API has neither and returns all
  9 797 nodes, 266 324 tokens, over 10× the client ceiling. The default is now the top
  level only: 979 tokens.
- `scripts/collect_corpus.py` and `scripts/measure_corpus.py`: snapshot real responses
  from a live account (PII masked before writing, corpus git-ignored) and measure what
  they cost. Corpus of 16 responses: 476 158 → 63 845 tokens.

### Notes
- Response shaping hangs on a contextvar: the dispatcher is one if-chain with 150 `_json`
  calls, and threading the tool name through every branch would be 150 chances to miss one.
- Null-stripping was implemented, measured at 0.2% on real data — the API returns zeros as
  the string `"0"` — and dropped.

## [2.2.1] — 2026-09-03

### Fixed
- `"default"` in the `limit` schema of `ozon_analytics` still advertised 1 000 while the
  handler had been lowered to 100. No error surfaced: the model reads the schema, believes
  it has 1 000 records, receives 100, and would report a conclusion about the whole
  catalogue. `test_limit_defaults_are_modest` now fails if any default exceeds 500.

## [2.2.0] — 2026-09-03

### Changed
- Definitions of 151 tools: 18 386 → 12 344 tokens with a single store configured.
  One-sentence descriptions (English wording plus Russian keywords for discovery),
  `shop_id` dropped from the schemas when only one store exists, empty schema fields no
  longer serialised, `[P1]`–`[P3]` prefixes removed and `[P0]` kept.
- Responses serialised without indentation; `ensure_ascii=False` retained, since escaping
  Cyrillic would add 32%.
- Default `limit` for `ozon_analytics` lowered from 1 000 to 100.

## [2.1.x] and earlier

See the git history and GitHub releases.

[2.4.3]: https://github.com/DeviceIngineering/ozon-mcp-server/releases/tag/v2.4.3
[2.4.2]: https://github.com/DeviceIngineering/ozon-mcp-server/releases/tag/v2.4.2
[2.4.1]: https://github.com/DeviceIngineering/ozon-mcp-server/releases/tag/v2.4.1
[2.4.0]: https://github.com/DeviceIngineering/ozon-mcp-server/releases/tag/v2.4.0
[2.3.0]: https://github.com/DeviceIngineering/ozon-mcp-server/releases/tag/v2.3.0
[2.2.1]: https://github.com/DeviceIngineering/ozon-mcp-server/releases/tag/v2.2.1
[2.2.0]: https://github.com/DeviceIngineering/ozon-mcp-server/releases/tag/v2.2.0
