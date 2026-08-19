# OpenAI Codex CLI

**SSE:** напрямую **не поддерживается** — нужен мост `mcp-remote`.

Codex CLI знает только два транспорта: **stdio** (ключ `command`) и
**Streamable HTTP** (ключ `url`). SSE в актуальном Config Reference не упоминается
ни как значение, ни как отдельный ключ. Поэтому наш `/sse` подключается через
stdio-мост.

Требуется Node.js 18+.

## Файл конфигурации

| ОС | Путь |
|----|------|
| macOS, Linux | `~/.codex/config.toml` |
| Windows | `%USERPROFILE%\.codex\config.toml` |

Графического интерфейса нет; управление — `codex mcp add|list|get|remove` и
команда `/mcp` в TUI.

## Без токена

```toml
[mcp_servers.ozon]
command = "npx"
args = ["-y", "mcp-remote", "http://localhost:8000/sse", "--transport", "sse-only"]
startup_timeout_sec = 30
```

## С `MCP_AUTH_TOKEN`

```toml
[mcp_servers.ozon]
command = "npx"
args = ["-y", "mcp-remote", "http://localhost:8000/sse",
        "--transport", "sse-only",
        "--header", "Authorization:${AUTH_HEADER}"]
env = { AUTH_HEADER = "Bearer <MCP_AUTH_TOKEN>" }
startup_timeout_sec = 30
```

Заголовок разбит на две части намеренно: пробелы внутри элемента `args` ломаются
в ряде клиентов, поэтому README `mcp-remote` советует форму `Authorization:${VAR}`,
а «Bearer …» держать в `env`.

Если сервер не на localhost (например `http://192.168.1.50:8000/sse`), добавьте
в `args` флаг `--allow-http`.

## То же самое одной командой

```bash
codex mcp add ozon -- npx -y mcp-remote http://localhost:8000/sse --transport sse-only
```

## Проверка

```bash
codex mcp list
codex mcp get ozon
```

и `/mcp` в TUI.

## Оговорки

- Ключ `experimental_use_rmcp_client = true` встречается в старых сторонних
  гайдах; в актуальном Config Reference его уже нет — не добавляйте вслепую.
- Дефолтный `startup_timeout_sec = 10` часто мал для холодного `npx` — поднимайте.
- Прямое подключение по `url` заработает только если у сервера появится
  Streamable HTTP-эндпоинт; тогда токен передаётся через `bearer_token_env_var`
  или `http_headers`/`env_http_headers`.
- Известный баг: при `bearer_token_env_var` команды `codex mcp list/get` показывают
  сервер аутентифицированным, даже если переменная процессу не видна
  ([openai/codex#30125](https://github.com/openai/codex/issues/30125)).

Источники:
[Codex Config Reference](https://learn.chatgpt.com/docs/config-file/config-reference),
[Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli),
[geelen/mcp-remote](https://github.com/geelen/mcp-remote) (проверено 19.08.2026).
