# SWDM — Steam Workshop Download Manager

[English](README.en.md) | [中文](README.md)

> A Python-based desktop app: browse and search the Steam Workshop, download mods **without a Steam account** (anonymous), and manage a categorized local mod library.
> Built by Atria-Dawn-Preview.

## Key Features

| Need | Implementation |
|---|---|
| ① Browse workshop items for a game — categories, search, popularity ranking | Game picker (favorites / custom AppID) → `/workshop/browse/` scraping + `GetPublishedFileDetails` batch metadata enrichment; keyword search, tag filtering, 6 sort orders (trend / newest / subscriptions / rating / views / favorites), client-side re-sort after enrichment so popularity ranking is accurate; paginated browsing |
| ② Keep downloaded mods organized and searchable | SQLite local library: multi-dimensional search by game / category / tags / status / keyword; `swdm_meta.json` metadata sidecar next to mod dirs; batch enable / disable, categorize, delete, open folder, export filtered results |
| ③ A fully-featured GUI | PySide6 five-tab interface: Workshop browse / Download queue (live progress bars) / My mod library / Settings (advanced) / Debug (live log stream, hidden by default); system tray, single instance, global crash logging |
| ④ Download auth-free mods without an account | SteamCMD `login anonymous` + `workshop_download_item`; falls back to manual login (with Steam Guard, keyring-encrypted password) when anonymous fails. Since 1.4.0: multi-provider chain with automatic fallback (GGNetwork anonymous proxy → CDN direct link → SteamCMD tail fallback) |

## Multi-Provider Download Chain (1.4.0)

Every download runs through a chain of providers built by the registry:

```
user's preferred channel → other enabled channels (by priority) → steamcmd (terminal tail fallback)
```

- A chain counts as **one attempt** — failing over inside the chain does not consume auto-retry budget.
- Channels that are disabled, unconfigured (missing key), or tripped by the circuit breaker (3 consecutive failures → 60s cooldown) are skipped.
- Default channel is still `steamcmd`, so the default path is byte-for-byte identical to 1.3.9 — nothing changes unless you switch.
- **GGNetwork** (`api.ggntw.com`) is an anonymous third-party workshop proxy — it resolves a workshop item URL to an official CDN direct link, no key required. It is a pilot: rate-limited to 20 resolve req/min (token bucket, burst 3) by self-discipline per the provider ToS; download speed is unaffected because the limiter only covers the resolve POST, not CDN transfer.

## Quick Start

```bash
pip install -r requirements.txt
python -m swdm.app        # or python swdm/app.py
```

On first launch it auto-detects an installed SteamCMD;
if none is present, deploy it in one click from **Settings → SteamCMD Engine** (downloaded from the official CDN and extracted).

## Technical Architecture

```
swdm/
├── app.py                     # entry (main + single instance + high DPI)
├── core/                      # core layer (GUI-independent, unit-testable)
│   ├── steam_api.py           # web API client (keyless metadata/collections/browse scraping/image cache)
│   ├── steamcmd_engine.py     # SteamCMD subprocess host (anonymous login/progress parse/auto-deploy/login test)
│   ├── downloader.py          # download queue + scheduling + auto-retry + provider chain fallback + library import
│   ├── providers/             # download provider abstraction (1.4.0)
│   │   ├── base.py            # ABC DownloadProvider + ProviderMeta + http_download (Range resume/cancel/429 report)
│   │   ├── registry.py        # ProviderRegistry: chain build / circuit breaker / channel list for UI
│   │   ├── cdn.py             # CDN direct-link channel (needs login)
│   │   ├── steamcmd.py        # SteamCMD channel — terminal tail fallback
│   │   └── ggnetwork.py       # anonymous third-party proxy channel (pilot)
│   ├── mod_library.py         # SQLite mod library (search/categorize/enable-disable/metadata sidecar)
│   ├── auth.py                # anonymous / manual login (keyring encryption)
│   ├── config.py              # persisted config (JSON, recursive merge)
│   ├── games.py               # 59 built-in workshop games + custom games
│   ├── logger.py              # rotating file log + in-memory ring buffer + GUI subscription
│   └── paths.py               # data dirs (portable mode supported)
├── gui/                       # PySide6 interface
│   ├── main_window.py         # main window / tray / menus / exception handling
│   ├── workshop_tab.py        # browse / search / download cards
│   ├── downloads_tab.py       # progress queue and history
│   ├── library_tab.py         # mod library management
│   ├── settings_tab.py        # all settings + login
│   ├── debug_tab.py           # live log (hidden by default)
│   ├── detail_dialog.py       # mod detail popup (description/comments/deps/preview images)
│   ├── workers.py             # QThread/QThreadPool bridge to core callbacks
│   ├── services.py            # service container
│   └── styles.py              # dark/light themes
└── resources/icon.ico
```

See [docs/project_structure.md](docs/project_structure.md) for a per-file responsibility index with iteration provenance.

## Data Directory

- Windows: `%APPDATA%\SWDM\` (config.json, logs/, library.db, cache/, mods/, steamcmd/)
- Portable mode: create a `portable.marker` file in the project root; data is then stored under `<root>/data/`

## Known Limitations

- Anonymous downloads only work for games whose workshop content does not require game-ownership verification.
- Category tags on the browse page are provided by the API `tags` field and filtered client-side; server-side tag filtering relies on the `requiredtags[]` parameter.
- On first use, SteamCMD may need to update itself, which takes a while.
- The GGNetwork channel has only been validated against offline mocks, never end-to-end over the real network. It is never on the default path — you must explicitly select it.

## Development

- Commit conventions and the bilingual documentation policy (incl. the comment-language rules for English/Chinese): [docs/git_workflow.md](docs/git_workflow.md)
- Full change history: [docs/changelog_1.3.8.md](docs/changelog_1.3.8.md) → [1.3.9](docs/changelog_1.3.9.md) → [1.4.0](docs/changelog_1.4.0.md)
- Tests: `tests/run_all.ps1` (offscreen Qt, ~59 scripts; set `PYTHONUTF8=1` on Windows)

## Roadmap (1.4.1, in development)

- Source comment / docstring bilingual adaptation (t30): module docstrings across `swdm/` rewritten English-first plus public API docstrings — done
- GGNetwork end-to-end testing over the real network (by a member with a real network path)
- Removal of the `cdn_downloader.py` compatibility facade (use `swdm.core.providers.cdn` instead)
- Download-tab polish items such as batch pause/resume

## License

See [LICENSE](LICENSE).
