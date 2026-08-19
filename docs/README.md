# Подключение Ozon MCP Server к клиентам

Сервер отдаёт MCP по транспорту **SSE**: `http://<host>:8000/sse`.
Авторизация — Bearer-токен из переменной `MCP_AUTH_TOKEN` (если она пуста,
авторизация не требуется). Клиенты, не умеющие передавать заголовки, могут
отдать токен параметром: `http://<host>:8000/sse?token=<MCP_AUTH_TOKEN>`.

| Клиент | SSE напрямую | Инструкция |
|--------|--------------|------------|
| Claude Code | да | [install-claude-code.md](install-claude-code.md) |
| Claude Desktop | нет, нужен мост `mcp-remote` | [install-claude-desktop.md](install-claude-desktop.md) |
| Cursor | да | [install-cursor.md](install-cursor.md) |
| Windsurf / Devin Desktop | да | [install-windsurf.md](install-windsurf.md) |
| VS Code (GitHub Copilot) | да | [install-vscode-copilot.md](install-vscode-copilot.md) |
| Cline | да (legacy SSE) | [install-cline.md](install-cline.md) |
| Continue.dev | да | [install-continue.md](install-continue.md) |
| Zed | не подтверждено, рекомендуем мост | [install-zed.md](install-zed.md) |
| JetBrains AI Assistant / Junie | да; заголовок в AI Assistant не документирован | [install-jetbrains.md](install-jetbrains.md) |
| Gemini CLI | да | [install-gemini-cli.md](install-gemini-cli.md) |
| OpenAI Codex CLI | нет, нужен мост `mcp-remote` | [install-codex.md](install-codex.md) |

Всё проверено по официальной документации клиентов 19 августа 2026. Где
документация молчит, в инструкции стоит пометка «не подтверждено» — это значит,
что вариант взят из практики сообщества и может отличаться в вашей версии.

## Про мост `mcp-remote`

Клиенты, которые умеют только stdio или только Streamable HTTP, подключаются к
SSE-серверу через [`mcp-remote`](https://github.com/geelen/mcp-remote) — небольшой
прокси, запускаемый через `npx`. Нужен Node.js 18+.

```bash
# без токена
npx -y mcp-remote http://localhost:8000/sse --transport sse-only

# с токеном
AUTH_HEADER="Bearer <MCP_AUTH_TOKEN>" npx -y mcp-remote http://localhost:8000/sse \
  --transport sse-only --header "Authorization:${AUTH_HEADER}"
```

Полезные флаги:

| Флаг | Назначение |
|------|------------|
| `--transport sse-only` | только SSE; без него мост сначала пробует Streamable HTTP |
| `--header "Name:value"` | произвольный заголовок; можно повторять |
| `--allow-http` | разрешить не-HTTPS адрес. Для `http://localhost` и `http://127.0.0.1` не нужен, для любого другого http-хоста обязателен |
| `--debug` | подробный лог в `~/.mcp-auth/{hash}_debug.log` |

Пробелы внутри одного элемента `args` ломаются в некоторых клиентах (Cursor,
Claude Desktop на Windows), поэтому во всех инструкциях заголовок передаётся как
`Authorization:${AUTH_HEADER}` с «Bearer …» в `env`.

Сброс залипших кредов моста: `rm -rf ~/.mcp-auth`.

## Как проверить, что сервер вообще жив

```bash
curl http://localhost:8000/api/health
# {"status":"ok","auth_enabled":false, ...}
```

`auth_enabled` показывает, задан ли `MCP_AUTH_TOKEN`. Если `true`, а клиент токен
не передаёт, `/sse` ответит `401 Unauthorized`.
