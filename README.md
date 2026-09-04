<div align="center">

[![Русский](https://img.shields.io/badge/%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B8%D0%B9-8B949E?style=for-the-badge)](README.ru.md)
![English](https://img.shields.io/badge/English-0A66C2?style=for-the-badge)
[![中文](https://img.shields.io/badge/%E4%B8%AD%E6%96%87-8B949E?style=for-the-badge)](README.zh.md)

</div>

# Ozon MCP Server

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![MCP tools](https://img.shields.io/badge/MCP%20tools-151-orange.svg)](docs/tools.md)
[![PyPI](https://img.shields.io/pypi/v/ozon-mcp-server.svg)](https://pypi.org/project/ozon-mcp-server/)
[![Transport](https://img.shields.io/badge/transport-stdio%20%7C%20SSE-lightgrey.svg)](#how-it-works)

Run your Ozon stores straight from a chat with an AI assistant: prices, promos,
advertising, orders, returns, reviews, finances — 151 tools on top of the Ozon
Seller API and Performance API (Ozon is Russia's largest marketplace; the Seller
API covers catalogue and operations, the Performance API covers paid ads).
Built for sellers who run **more than one store**: every call takes a `shop_id`,
and API keys stay encrypted on your own server — nothing leaves it.
What sets it apart from other Ozon MCP servers: it covers advertising as well as
the Seller API, and its built-in diagnostics tell you which Ozon endpoints broke
before your assistant runs into them.

Selling on Wildberries too? There is the same server for WB —
[wb-mcp-server](https://github.com/DeviceIngineering/wb-mcp-server).

This is the author's own working tool: more than five months of daily use, around
twenty seller accounts, 151 tools. It gets updated when he needs it updated — see
[Updates and support](#updates-and-support) for what that means for you.

> The per-client installation guides in `docs/` are currently **Russian only**.
> The configuration in them is ready-to-paste JSON, which reads the same in any
> language: file paths, the URL `http://localhost:8000/sse`, and the header
> `Authorization: Bearer <MCP_AUTH_TOKEN>`.

```
You: Which of my products is Ozon planning to pull into a promo?
You: Show ad campaign spend for the week and stop the ones burning money.
You: Which products have a worse price index than their competitors?
You: Reply with a thank-you to every new 5-star review.
```

![Ozon MCP Server dashboard](https://raw.githubusercontent.com/DeviceIngineering/ozon-mcp-server/main/docs/img/dashboard.png)

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

The full numbered list, with a description and the parameters of every tool, is in
**[docs/tools.md](docs/tools.md)**. It is generated from `ozon_mcp/server.py` (the
`TOOLS` constant) — the same thing `tools/list` returns to any MCP client.

## Quick start

### Option 1: one command, no Docker

The server speaks stdio, which is how Claude Desktop, Cursor, VS Code and other
MCP clients connect to it. Nothing to build:

```bash
uvx ozon-mcp-server
```

Or via pip:

```bash
pip install ozon-mcp-server
ozon-mcp
```

Client configuration (for example `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ozon": {
      "command": "uvx",
      "args": ["ozon-mcp-server"],
      "env": {
        "OZON_CLIENT_ID": "your Client-Id",
        "OZON_API_KEY": "your API key",
        "DATA_DIR": "~/.ozon-mcp"
      }
    }
  }
}
```

Point `DATA_DIR` at any writable directory — it holds stores, keys and statistics.
The default is `/data`, which is the path used inside Docker.

### Option 2: Docker with the web dashboard

Use this if you want the dashboard, Ozon API diagnostics and browser-based store
management. Five commands:

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

To stop: `docker compose down` (the data stays in the `ozon_data` volume).
Logs: `docker compose logs -f`.

### Without Docker

```bash
python3 -m venv .venv && source .venv/bin/activate
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

Stores are added in the web UI, and every tool takes a required `shop_id`;
`ozon_list_shops` tells you which ones exist. In chat it looks like this:
"show me the stock in store `alpha`".

The real gain is not the switching itself but that **a strategy is written once and
rolled out to every account**: a rule about prices, review replies or ad bids
applies to all stores at once — no logging in and out of seller accounts, no
copying keys between client configs.

The price you pay is a shared IP. Every account talks to Ozon from one address:
the server the MCP runs on. Ozon's rate limits are counted per address among other
things, so the more accounts you have and the harder your strategies work them, the
closer the combined traffic gets to the threshold where throttling or a block kicks in.

- there is **no** limit on the number of stores in the code;
- the real ceiling comes from Ozon's per-IP limits, not from this server;
- around twenty accounts is the author's own estimate of where the traffic still
  stays in the safe zone;
- beyond that, spread the stores across several servers with different addresses.

You can see the limit approaching, and the place to see it is the web UI: failed
pings and diagnostics warnings start piling up, and the error share in the call
statistics jumps. The dashboard also tells the two cases apart — mass throttling
looks like many tools degrading at once, a broken endpoint like a single one.

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
- The server does not terminate HTTPS. If you need TLS from outside, put a reverse
  proxy in front.

## The web UI: every call is visible

With a typical MCP server, calls vanish into the void: the assistant did
something, but what exactly, how long it took and what error it hit is known only
to the assistant. Here every call gets a line in the log, and every broken tool
gets a marker on the dashboard. For a tool that moves real money in a store, that
is not decoration — it is the condition for trusting it.

The call statistics and check history are not synthetic: they come from more than
five months of daily use across roughly twenty seller accounts. The list of caught
Ozon API changes in the limitations section comes from the same place — it was
read off the degradation log, not copied from the documentation.

### Dashboard `/`

The screenshot is at the top of this page.

- Four counters at the top: total calls, calls today, errors, and average call
  duration in milliseconds.
- Top 10 tools: call count, average duration, and how many of those calls failed.
- A feed of the last 50 calls: timestamp, `shop_id`, tool name, duration, success
  or failure, and the error text.
- A per-store filter (`/?shop=alpha`) — the same figures for a single account.
- Two banners surface at the top: degraded tools, and "the last Ozon API check
  found problems".

### Stores `/shops`

![Stores page](https://raw.githubusercontent.com/DeviceIngineering/ozon-mcp-server/main/docs/img/shops.png)

Accounts are added and removed right in the browser, with no file editing and no
container restart. The "Проверить" (Test) button makes a live request to both APIs
(`POST /api/shops/{shop_id}/test`), so keys are verified when you add them rather
than during the first real call in the middle of a task. Tokens are encrypted with
Fernet, the encryption key lives in `DATA_DIR/.encryption_key`, and the UI shows
keys masked.

### Diagnostics `/diagnostics`

![Diagnostics page](https://raw.githubusercontent.com/DeviceIngineering/ozon-mcp-server/main/docs/img/diagnostics.png)

*(the screenshot shows a demo store with deliberately invalid keys, which is why
every probe is red)*

- Per store: whether keys are set, Ozon host availability, 12 Seller API category
  probes, and a Performance API key check.
- A background check every `HEALTH_CHECK_INTERVAL_MIN` minutes (30 by default,
  `0` disables it), plus a "Проверить сейчас" (Check now) button for an immediate
  run (`POST /api/diagnostics/run`).
- Check history: time, store, status, number of failed pings, number of failed
  probes, and the warning texts. The UI shows the last 30 entries; up to 1000 are
  kept in the database with automatic rotation.
- The same data is available from chat through the `ozon_diagnostics` tool.

### Degradation detector

The server notices on its own that Ozon broke or switched off an endpoint — not
from the documentation and not from work that failed, but from its own statistics.
A tool whose last three calls in a row failed while earlier calls succeeded lands
in the degradation list, which shows the tool name, the time of the last successful
call, the number of consecutive errors, and the text of the latest one. On the
dashboard that is a red banner; on the diagnostics page, a table.

What this buys you: a change on Ozon's side becomes visible the day it happens,
not a week later when you discover prices haven't been updating. The same list is
available from chat via `ozon_degradations`.

### JSON for external monitoring

All of the above can be scraped programmatically, not just looked at:

| Endpoint | What it returns |
|----------|-----------------|
| `GET /api/health` | service status, whether authentication is on, recent checks, degraded tools |
| `GET /api/stats` | the same summary as the dashboard; `?shop=` narrows it to one store |
| `GET /api/diagnostics/{shop_id}` | a full live diagnostic run for one store |

That is enough to wire the server into Zabbix, Uptime Kuma, or a plain `curl` in cron.

## Context budget

Two things are paid in tokens: tool definitions, loaded once per session, and tool
responses, paid on every call. Both were measured on a live seller account rather
than estimated — `scripts/collect_corpus.py` takes a snapshot of read-only tools
(PII masked before anything is written to disk, the corpus stays out of the repo),
`scripts/measure_corpus.py` reports what it costs.

**Definitions.** 151 tools cost **12 300 tokens** with a single store configured,
down from 18 386: one-sentence descriptions, `shop_id` dropped from the schemas when
only one store exists, no empty schema fields.

**Responses.** The real problem turned out to be a handful of giant payloads:

| tool | before | after |
|---|---:|---:|
| `ozon_category_tree` — a 9 797-node tree | 266 324 | 979 |
| `ozon_get_prices` — 93 % of the weight is promo history | 52 879 | 8 679 |
| `ozon_returns_fbo` — 50 returns with full logistics | 24 277 | 8 458 |
| `ozon_warehouse_list` — 99 % of the weight is a year of timetables | 20 132 | 370 |
| **corpus of 16 live responses** | **476 158** | **63 845** |

What the server does about it:

- **`view: compact | full`.** Heavy tools return the fields they are called for;
  `view="full"` gives the raw API response, and the answer states which fields were
  hidden so the model knows what it can ask for.
- **Truncation signal.** When exactly `limit` records come back, the answer says the
  data is partial — otherwise the model reasons about a slice and presents it as the
  whole catalogue.
- **Size guard.** A response that would not fit the client's output ceiling
  (`MAX_MCP_OUTPUT_TOKENS`, 25 000 by default in Claude Code) is cut server-side with
  a count of what was left out, instead of being silently truncated on arrival.
- **Search and depth for the category tree.** The API has neither and returns all
  9 797 nodes; `search` finds a category, `depth` controls the level, and the default
  is the top level only.

Notes arrive as separate content blocks rather than a field inside the JSON: several
Ozon endpoints return an array at the top level, and wrapping it would break every
path into the data.

**Tool profiles.** A client without tool search pays for the whole catalogue on every
request. `OZON_TOOLSETS` keeps only the profiles you use, cut along working tasks
rather than documentation sections:

| `OZON_TOOLSETS` | tools | tokens |
|---|---:|---:|
| empty (default) | 151 | 12 686 |
| `pricing,ads` | 57 | 5 425 |
| `orders` | 33 | 2 611 |

The `core` profile — stores, diagnostics, degradations, company — is always on:
diagnostics are needed exactly when something is broken. Disabled profiles are listed
in the `ozon_list_shops` description, and calling a disabled tool answers which profile
contains it, so the assistant names the reason instead of saying "this is not possible".

Claude Code needs none of this: it has tool search enabled by default. Cursor, Cline,
Continue and Claude Desktop fetch `tools/list` whole — profiles are for them.

## Design decisions

- **151 narrow tools, not a few generic ones.** Collapsing them into `action`-style
  endpoints would save definition tokens and change the class of failure: instead of
  "no such tool" you get a wrong call with a side effect, and some of these tools set
  prices and start ad campaigns.
- **The server diagnoses itself.** `ozon_diagnostics` checks host availability and
  runs a light real request across 12 Seller API categories plus the Performance API
  keys; `ozon_degradations` reports which tools used to work and now fail steadily.
  Ozon retires endpoints without notice, so "is it my keys or did the API move" has to
  be answerable in one call.
- **`compact` is the default for heavy tools.** The corpus showed the hidden fields are
  promo history, warehouse timetables and logistics internals — not the data decisions
  are made from — and the response says what was hidden.
- **Response shaping hangs on a contextvar.** The dispatcher here is one long if-chain
  with 150 `_json` calls; threading the tool name and arguments through every branch by
  hand would be 150 edit sites and 150 chances to miss one.
- **`shop_id` disappears from schemas with one store**, and comes back the moment a
  second one appears.
- **`mcp<2` is pinned deliberately** — the 2.0 low-level API drops the decorator
  handlers this server is built on; the pin is documented where it is set.
- **Keys are encrypted at rest** (Fernet, key in the data volume) and masked in the UI;
  the corpus collector masks personal data before writing a file.

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

The hosts the server talks to:

| API | Base URL | Authorization |
|-----|----------|---------------|
| Seller API | api-seller.ozon.ru | `Client-Id` and `Api-Key` headers |
| Performance API (ads) | api-performance.ozon.ru | OAuth `client_credentials`, 30-minute token |

Non-obvious things:

- Ozon returns ad bids and budgets in **micro-rubles**: `1000000` = 1 ₽. Don't be
  surprised by seven-digit numbers.
- A `403` on reviews and questions is not a breakage — it means no Premium Plus
  subscription. Diagnostics does not count those as errors.
- Ozon API keys became time-limited after the 2026-02-13 rotation — 180 days. The
  expiry is exposed explicitly: `POST /v1/roles` returns `expires_at`, so you can
  warn ahead of time instead of catching a `401` in the probes.
- Asynchronous ad statistics: one report at a time, ≤10 campaigns, ≤62 days. The
  tool waits up to about 2 minutes for the report to be ready.
- Supply-order statuses in API v3 are integers 1–8, not strings.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_AUTH_TOKEN` | empty | Bearer token for `/sse`. Empty = no authentication |
| `HEALTH_CHECK_INTERVAL_MIN` | `30` | background diagnostics interval, `0` disables it |
| `PORT` | `8000` | HTTP server port |
| `OZON_TOOLSETS` | empty | comma-separated tool profiles: `pricing`, `ads`, `catalog`, `orders`, `analytics`, `feedback`, `finance`; empty means all 151 |
| `OZON_MAX_RESPONSE_CHARS` | `60000` | size-guard threshold for a single response |
| `DATA_DIR` | `/data` | directory holding `shops.json`, `stats.db`, `.encryption_key` |
| `OZON_CLIENT_ID`, `OZON_API_KEY` | empty | Seller API keys for the `default` store, if you'd rather not use the UI |
| `OZON_PERF_CLIENT_ID`, `OZON_PERF_CLIENT_SECRET` | empty | the same for the Performance API |

## Known Ozon API limitations (as of August 2026)

- Advertising: the API can only create "Trafarety" CPC campaigns; budgets and bids
  are in micro-rubles; there is no official way to read the ad account balance.
- "Pay per order": bids have been fixed since February 2025 — you can only turn
  the promotion on or off.
- Reviews, questions and part of analytics require a Premium Plus subscription
  (error code 7).
- Funnel metrics in `ozon_analytics` are marked deprecated by Ozon — use
  `ozon_product_queries` for search positions.
- **Endpoints Ozon is switching off in autumn 2026.** Dates from the official
  @OzonSellerAPI channel, verified against live seller accounts
  ([issue #6](https://github.com/DeviceIngineering/ozon-mcp-server/issues/6),
  thanks to [@standlord-prog](https://github.com/standlord-prog)):

  | path | goes dark | replacement |
  |---|---|---|
  | `/v3/posting/fbs/list` | 2026-08-31 | `/v4/posting/fbs/list` — **done in v2.1.0** |
  | `/v2/posting/fbo/list` | 2026-08-31 | `/v3/posting/fbo/list` — **done in v2.1.0** |
  | `/v3/posting/fbs/unfulfilled/list` | 2026-08-31 | no replacement: filtered out of `/v4/posting/fbs/list` by status — **done in v2.1.0** |
  | `/v2/posting/fbs/act/create` | 2026-09-07 | `/v1/carriage/create` + `/v1/carriage/approve` — in progress |
  | `/v3/finance/transaction/list` | 2026-09-08 | `/v1/finance/accrual/by-day` — in progress |
  | `/v3/finance/transaction/totals` | 2026-09-08 | same — in progress |

  `/v4/posting/fbs/list` is not a rename of v3: `postings` sit at the top level
  rather than under `result`, and pagination is cursor-based (`has_next` + `cursor`)
  instead of `offset`.
- `ozon_finance_cash_flow` and `ozon_finance_accruals` already run on the new paths
  (`/v1/finance/cash-flow-statement/list`, `/v1/finance/accrual/by-day`).
- `ozon_product_stocks_by_warehouse` uses v2 because v1 is switched off on 2026-04-07.
- Digital FBS handover acts were removed by Ozon on 2026-03-22 — the regular act
  is used instead.
- The Ozon API has no "edit a review reply" method: the reply is deleted and
  written again.

This list is not a rewrite of the reference: it comes from the degradation log and
five months of daily calls, cross-checked against docs.ozon.ru as of August 2026.

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
├── docs/                # client connection guides + tool reference
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

## The same server for Wildberries

[**wb-mcp-server**](https://github.com/DeviceIngineering/wb-mcp-server) is the same
tool for the other marketplace (Wildberries is the other large Russian
marketplace): same architecture, same web UI with dashboard and diagnostics, same
multi-store model via `shop_id`, same SSE transport, same ways of connecting
clients.

|  | Ozon MCP Server | WB MCP Server |
|---|---|---|
| Port | 8000 | 8001 |
| Tools | 151 | 202 |
| API | Ozon Seller API + Performance API (ads) | Wildberries Seller API |

In practice that means two things:

- **The second server takes no new learning.** Once you have set up one, the other
  starts the same way; only the port (8001 instead of 8000) and the tool set differ.
- **You can run both on one machine.** Different ports, data in separate Docker
  volumes, no conflict. In your client they are simply two MCP servers: `ozon` at
  `http://localhost:8000/sse` and `wb` at `http://localhost:8001/sse`.

Sharing one machine does not hurt on rate limits either: both go out from the same
IP, but Ozon and Wildberries count limits on their own side — they are different
marketplaces. The cap on the number of seller accounts described in the multi-store
section applies within each marketplace separately.

## From API access to a working repricer

This server gives a model access to the seller account. Deciding *what* the price
should be is a separate job, and [**ozon-wildberries-repricer**](https://github.com/DeviceIngineering/ozon-wildberries-repricer)
does it: it holds a reference price, computes a break-even floor from each
marketplace's real fees, pulls products out of promotions that would push them
under cost, and can search for a better price by running a controlled experiment
on live sales.

It covers Ozon, Wildberries and Yandex Market in one place, and it has its own
HTTP control plane for LLM agents — with the rails a model needs: a price move
that would trigger Wildberries quarantine is walked over several runs, prices are
read back three minutes later because marketplaces report success for changes they
did not make, and several agents working the same catalogue cannot overwrite each
other's decisions.

Run it without a marketplace account: `npm run demo` seeds a synthetic catalogue
and starts the app.

## Updates and support

Ozon changes its API constantly: endpoints get added, renamed and switched off
(the limitations section above lists what has been caught so far). This server is
the author's working tool, and it gets updated **when he needs it updated** — that
is, when a change breaks something in his own stores. More than five months of
daily use, and commits appear when Ozon breaks something, not on a schedule: a gap
between commits usually means everything is working. The upside is that the code is
proven by real daily use rather than published and forgotten; the downside is that
there is no release schedule and no commitment on turnaround.

If you need a fix urgently, write to **d0371153@gmail.com**.
Issues and pull requests are welcome too, and they do get read.

## Acknowledgements

- [@standlord-prog](https://github.com/standlord-prog):
  - [issue #6](https://github.com/DeviceIngineering/ozon-mcp-server/issues/6) — the breakdown
    of Ozon endpoints being switched off, verified against live seller accounts: dates,
    replacements and three gotchas in the move to `/v4`. Separately — the warning that
    `/v1/carriage/create` has no required fields and an empty `{}` body creates a real
    shipment, and the correction about `POST /v1/roles` returning `expires_at`.
    Version **v2.1.0** is built on that work.
  - [PR #7](https://github.com/DeviceIngineering/ozon-mcp-server/pull/7) — found and fixed
    blind diagnostics: in stdio mode call statistics were never initialised, so
    `ozon_degradations` answered "no degradations" to every question — even when every
    single call was failing. The tool is marked [P0] and is asked precisely when something
    has broken, which makes a silent false negative worse than having no tool at all. The
    PR does not just fix the wiring: it also separates "no data" from "no degradations"
    and adds an integration test over stdio with a real MCP client. Shipped in **v2.1.2**.

Version history: [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).

## MCP Registry

Published in the official [MCP Registry](https://registry.modelcontextprotocol.io/):

```
mcp-name: io.github.DeviceIngineering/ozon-mcp-server
```
