[Русский](README.md) · English · [中文](README.zh.md)

# Ozon MCP Server

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![MCP tools](https://img.shields.io/badge/MCP%20tools-151-orange.svg)](#what-it-does)

Run your Ozon stores straight from a chat with an AI assistant: prices, promos,
advertising, orders, returns, reviews, finances — 151 tools on top of the Ozon
Seller API and Performance API (Ozon is Russia's largest marketplace; the Seller
API covers catalogue and operations, the Performance API covers paid ads).
Built for sellers who run **more than one store**: every call takes a `shop_id`,
and API keys stay encrypted on your own server — nothing leaves it.
What sets it apart from other Ozon MCP servers: it covers advertising as well as
the Seller API, and its built-in diagnostics tell you which Ozon endpoints broke
before your assistant runs into them.

This is the author's own working tool — used daily and updated when he needs it
updated. See [Updates and support](#updates-and-support) for what that means for you.

> The per-client installation guides in `docs/` are currently **Russian only**.
> The configuration in them is ready-to-paste JSON, which reads the same in any
> language: file paths, the URL `http://localhost:8000/sse`, and the header
> `Authorization: Bearer <MCP_AUTH_TOKEN>`.

![Ozon MCP Server dashboard](docs/img/dashboard.png)

## What it does

| Group | Tools | What's inside |
|-------|-------|---------------|
| Promotions and discounts | 14 | Ozon promotions (list, candidates, join/leave), seller's own promotions, "I want a discount" buyer requests |
| Prices and pricing strategies | 14 | setting prices and the minimum price, price index, minimum-price timer, automatic strategies that track competitors |
| Advertising (Performance API) | 22 | "Trafarety" CPC campaigns (Ozon's sponsored-placement format), bids and budgets, "Pay per order" (CPO), per-product and daily statistics |
| Products | 21 | listings and cards, attributes, stock, import and bulk updates, media, archive, certificates |
| FBS and FBO orders | 17 | unfulfilled orders, packing (v4), labels, cancellations, handover acts, country of origin |
| Returns and cancellations | 10 | unified FBO+FBS returns list, rFBS claims that need a seller decision, cancellation requests |
| Reviews, questions, chats | 13 | reviews and replies, buyer questions, chat conversations (v3) |
| Warehouses and reports | 8 | FBS warehouses, delivery methods, generating and downloading reports |
| Finances | 7 | balance, transactions, accruals, realization report, mutual settlements, cash flow |
| Categories, brands, certificates | 7 | category tree, attributes and their allowed values, certificates |
| Analytics | 5 | SKU analytics, stock and turnover, product positions in Ozon search, top search queries |
| FBO supplies | 4 | supply orders (v3), counters, timeslots |
| Rating | 2 | current seller rating and its history |
| Diagnostics | 2 | self-check of Ozon API availability, degradation detector |
| Notifications | 2 | push webhook subscriptions and the event-type reference |
| Company | 2 | seller details and tariffs |
| Stores | 1 | list of connected stores and their `shop_id` |

FBO and FBS are Ozon's fulfilment models: FBO ships from Ozon's warehouses,
FBS from yours, rFBS is FBS with your own delivery.

For the full list of tool names see `ozon_mcp/server.py` (the `TOOLS` constant),
or call `tools/list` from any MCP client.

## Quick start

You need Docker. Five commands:

```bash
git clone https://github.com/DeviceIngineering/ozon-mcp-server.git
cd ozon-mcp-server
cp .env.example .env               # fine as-is for a trusted local network
docker compose up -d --build       # builds the image, serves on port 8000
open http://localhost:8000/shops   # add a store and its Ozon API keys
```

What each step does:

- `.env` — every variable is optional. Store keys are easier to enter in the web
  UI than here. The one thing worth setting up front, if the server is reachable
  by anyone but you, is `MCP_AUTH_TOKEN` (generate one with `openssl rand -hex 32`).
- `docker compose up -d --build` — builds the image from the `Dockerfile`, maps
  port `8000:8000` and creates the `ozon_data` volume for stores, keys, call
  statistics and diagnostics history. `restart: unless-stopped` brings the
  container back up after a reboot.
- `/shops` — the add-store form: `shop_id` (the handle you'll use in chat), a
  display name, Client-Id + Api-Key for the Seller API, and Client-Id +
  Client-Secret for the Performance API. The "Проверить" (Test) button makes a
  live request to Ozon and tells you whether the keys were accepted.

Once it's running:

| Address | What it is |
|---------|------------|
| `http://localhost:8000/` | dashboard: call counters, errors, degradations |
| `http://localhost:8000/shops` | stores and keys |
| `http://localhost:8000/diagnostics` | Ozon API diagnostics |
| `http://localhost:8000/api/health` | health endpoint, JSON |
| `http://localhost:8000/sse` | **the MCP endpoint** — this is what clients point at |

Note that the web UI is in Russian.

### Without Docker

```bash
pip install .
DATA_DIR=./data PORT=8000 ozon-mcp-web
```

`DATA_DIR` defaults to `/data`, so when running locally be sure to point it at a
directory you can write to.

## Installing into clients

The transport is SSE at `http://<host>:8000/sse`. SSE support differs between
clients: some speak it directly, others need the `mcp-remote` bridge. There is one
guide per client, with config paths for macOS, Linux and Windows and ready-made
JSON — **in Russian**, but the JSON blocks are language-neutral:

| Client | SSE directly | Guide |
|--------|--------------|-------|
| Claude Code | yes | [docs/install-claude-code.md](docs/install-claude-code.md) |
| Claude Desktop | no, `mcp-remote` bridge | [docs/install-claude-desktop.md](docs/install-claude-desktop.md) |
| Cursor | yes | [docs/install-cursor.md](docs/install-cursor.md) |
| Windsurf / Devin Desktop | yes | [docs/install-windsurf.md](docs/install-windsurf.md) |
| VS Code (GitHub Copilot) | yes | [docs/install-vscode-copilot.md](docs/install-vscode-copilot.md) |
| Cline | yes | [docs/install-cline.md](docs/install-cline.md) |
| Continue.dev | yes | [docs/install-continue.md](docs/install-continue.md) |
| Zed | unconfirmed, bridge recommended | [docs/install-zed.md](docs/install-zed.md) |
| JetBrains AI Assistant / Junie | yes | [docs/install-jetbrains.md](docs/install-jetbrains.md) |
| Gemini CLI | yes | [docs/install-gemini-cli.md](docs/install-gemini-cli.md) |
| OpenAI Codex CLI | no, `mcp-remote` bridge | [docs/install-codex.md](docs/install-codex.md) |

The shortest example, Claude Code:

```bash
claude mcp add --transport sse ozon http://localhost:8000/sse \
  --header "Authorization: Bearer <MCP_AUTH_TOKEN>"
```

Client summary and the bridge reference: [docs/README.md](docs/README.md).

## Multi-store and security

You can add as many stores as you like. Every tool takes a required `shop_id`;
`ozon_list_shops` tells you which ones exist. In chat it looks like this:
"show me the stock in store `alpha`".

![Stores page](docs/img/shops.png)

How keys are stored:

- on first use, `.encryption_key` — a Fernet key — is created in `DATA_DIR`;
- store keys are encrypted with it and kept in `DATA_DIR/shops.json`;
- the web UI shows keys masked (`abc***xyz`), and saving a masked value does not
  overwrite the real one;
- under Docker all of this lives in the `ozon_data` volume. To move to another
  machine, copy the whole volume — otherwise you lose the encryption key
  (see [DEPLOY.md](DEPLOY.md), Russian).

What to know about access:

- `MCP_AUTH_TOKEN` protects **only** `/sse`. Pass it as the
  `Authorization: Bearer …` header or as a `?token=…` query parameter.
- An empty `MCP_AUTH_TOKEN` means no authentication at all. Only acceptable on a
  trusted network.
- The web UI (`/`, `/shops`, `/diagnostics`) and `/api/*` are **not** behind the
  token: anyone who can reach the port sees the dashboard and can add stores.
- Do not expose port 8000 to the internet directly. For remote access use
  Tailscale or a VPN.

## How it works

A single Docker container running a FastAPI application that is both the MCP
server and the web UI.

- **`ozon_mcp/server.py`** — the MCP server itself. The `TOOLS` list describes all
  151 tools (name, description, JSON schema for the arguments) and the `call_tool`
  handler routes each call to the right Ozon client method. Clients are pooled per
  `shop_id`, so switching stores reconnects nothing.
- **`ozon_mcp/client.py`** — two HTTP clients: `OzonSellerClient` (`Client-Id` /
  `Api-Key` headers) and `OzonPerformanceClient` (a `client_credentials` token that
  lives 30 minutes and refreshes itself).
- **`ozon_mcp/app.py`** — FastAPI: the `/sse` endpoint on top of
  `SseServerTransport`, Bearer-token checking, the dashboard/stores/diagnostics
  pages, and the background health-check task.
- **`ozon_mcp/settings.py`** — stores and keys: Fernet encryption, masking for the
  UI, picking up keys from environment variables as a store called `default`, and
  migrating the old single-store `settings.json` into `shops.json`.
- **`ozon_mcp/diagnostics.py`** — probes: pinging Ozon hosts plus lightweight real
  requests across 12 Seller API categories, and a Performance API key check.
- **`ozon_mcp/stats.py`** — SQLite via `aiosqlite`: every tool call with its
  duration and outcome, health-check history, degradation calculation.

Non-obvious things:

- Ozon returns ad bids and budgets in **micro-rubles**: `1000000` = 1 ₽. Don't be
  surprised by seven-digit numbers.
- A `403` on reviews and questions is not a breakage — it means no Premium Plus
  subscription. Diagnostics does not count those as errors.
- Ozon API keys carry no expiry date; you only learn one expired from a `401` in
  the probes.
- Asynchronous ad statistics: one report at a time, ≤10 campaigns, ≤62 days. The
  tool waits up to about 2 minutes for the report to be ready.
- Supply-order statuses in API v3 are integers 1–8, not strings.

## Diagnostics

![Diagnostics page](docs/img/diagnostics.png)

*(the screenshot shows a demo store with deliberately invalid keys, which is why
every probe is red)*

- The `/diagnostics` page: per store — host availability, 12 Seller API category
  probes, a Performance API key check, and the check history.
- A background check runs every `HEALTH_CHECK_INTERVAL_MIN` minutes (30 by
  default, `0` disables it).
- Degradation detector: a tool that used to work and now fails consistently raises
  a "Ozon may have changed the API" alert on the dashboard.
- From chat: the `ozon_diagnostics` and `ozon_degradations` tools.
- Run a check immediately: the button on the page, or `POST /api/diagnostics/run`.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_AUTH_TOKEN` | empty | Bearer token for `/sse`. Empty = no authentication |
| `HEALTH_CHECK_INTERVAL_MIN` | `30` | background diagnostics interval, `0` disables it |
| `PORT` | `8000` | HTTP server port |
| `DATA_DIR` | `/data` | directory holding `shops.json`, `stats.db`, `.encryption_key` |
| `OZON_CLIENT_ID`, `OZON_API_KEY` | empty | Seller API keys for the `default` store, if you'd rather not use the UI |
| `OZON_PERF_CLIENT_ID`, `OZON_PERF_CLIENT_SECRET` | empty | the same for the Performance API |

## Known Ozon API limitations (as of June 2026)

- Advertising: the API can only create "Trafarety" CPC campaigns; budgets and bids
  are in micro-rubles; there is no official way to read the ad account balance.
- "Pay per order": bids have been fixed since February 2025 — you can only turn
  the promotion on or off.
- Reviews, questions and part of analytics require a Premium Plus subscription
  (error code 7).
- Funnel metrics in `ozon_analytics` are marked deprecated by Ozon — use
  `ozon_product_queries` for search positions.
- `/v3/finance/transaction/*` is being switched off on 2026-07-06; the replacements
  are already wired in (`ozon_finance_cash_flow`, `ozon_finance_accruals`).
- `ozon_product_stocks_by_warehouse` uses v2 because v1 is switched off on 2026-04-07.
- Digital FBS handover acts were removed by Ozon on 2026-03-22 — the regular act
  is used instead.
- The Ozon API has no "edit a review reply" method: the reply is deleted and
  written again.

## What changed in version 2.0

A full revision against the June 2026 Ozon API, verified by running real requests
rather than reading docs: the unified returns list, cancellations v2, realization
v2, ship v4, supply-order v3, real pricing strategies and "I want a discount",
the seller's own promotions, the new advertising model (Trafarety CPC + "Pay per
order"), diagnostics with a degradation detector, and authentication on the MCP
endpoint.

## Project layout

```
ozon-mcp-server/
├── docker-compose.yml   # port 8000, ozon_data volume
├── Dockerfile           # python:3.12-slim, uvicorn
├── DEPLOY.md            # deploying to a dedicated machine, moving data
├── docs/                # client connection guides
└── ozon_mcp/
    ├── server.py        # MCP server: 151 tools, multi-store
    ├── client.py        # Seller API + Performance API
    ├── app.py           # FastAPI: SSE, web, auth, health loop
    ├── diagnostics.py   # category probes, degradation detector
    ├── settings.py      # stores and keys (Fernet)
    ├── stats.py         # call statistics and check history (SQLite)
    └── templates/       # dashboard, diagnostics, shops
```

Deploying to a dedicated machine and moving stores across:
[DEPLOY.md](DEPLOY.md) (Russian).

## Updates and support

Ozon changes its API constantly: endpoints get added, renamed and switched off
(the limitations section above lists what has been caught so far). This server is
the author's working tool, and it gets updated **when he needs it updated** — that
is, when a change breaks something in his own stores. The upside is that the code
is proven by real daily use rather than published and forgotten; the downside is
that there is no release schedule and no commitment on turnaround.

If you need a fix urgently, write to **d0371153@gmail.com**.
Issues and pull requests are welcome too, and they do get read.

## License

MIT — see [LICENSE](LICENSE).
