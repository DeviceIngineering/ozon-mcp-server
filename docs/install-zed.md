# Zed

**SSE:** прямая поддержка **не подтверждена** — рекомендуем мост `mcp-remote`.

Документация Zed описывает удалённые MCP-серверы только как `url` + `headers` с
OAuth-флоу, что соответствует транспорту Streamable HTTP; слово SSE в разделе про
MCP не встречается вовсе. Есть закрытый issue
[zed#41716](https://github.com/zed-industries/zed/issues/41716) «Can't detect local
MCP server over SSE transport» (ноябрь 2025), где сервер на `/sse` работал в
VS Code, но не в Zed; официальной позиции мейнтейнеров там нет. Поэтому прямой
вариант ниже дан как «попробуйте», а надёжный — через мост.

## Файл конфигурации

`settings.json`, ключ `context_servers`. Точные пути по ОС в разделе про MCP
не приведены; стандартные (**официально в этом разделе не подтверждены**):

| ОС | Путь |
|----|------|
| macOS, Linux | `~/.config/zed/settings.json` |
| Windows | `%APPDATA%\Zed\settings.json` |
| Проект | `.zed/settings.json` |

Через интерфейс: **Settings → AI → MCP Servers → Add Server → Add Remote Server**
(для локальных процессов — **Add Local Server**). Файл открывается командой
`zed: open settings file`.

## Надёжный вариант — через мост `mcp-remote`

Требуется Node.js 18+.

Без токена:

```json
{
  "context_servers": {
    "ozon": {
      "command": {
        "path": "npx",
        "args": ["-y", "mcp-remote", "http://localhost:8000/sse", "--transport", "sse-only"]
      }
    }
  }
}
```

С токеном:

```json
{
  "context_servers": {
    "ozon": {
      "command": {
        "path": "npx",
        "args": [
          "-y", "mcp-remote", "http://localhost:8000/sse",
          "--transport", "sse-only",
          "--header", "Authorization:${AUTH_HEADER}"
        ],
        "env": { "AUTH_HEADER": "Bearer <MCP_AUTH_TOKEN>" }
      }
    }
  }
}
```

Форма объекта `command: { path, args, env }` взята из примеров сообщества;
в официальной документации Zed схема локального сервера описана как «command и
args» — при расхождении сверьтесь с документацией своей версии.

Если сервер живёт не на localhost (например `http://192.168.1.50:8000/sse`),
добавьте флаг `--allow-http`: для `http://localhost` и `http://127.0.0.1` он
не нужен, для остальных http-адресов — обязателен.

## Прямой вариант (не подтверждён)

```json
{
  "context_servers": {
    "ozon": {
      "url": "http://localhost:8000/sse",
      "headers": { "Authorization": "Bearer <MCP_AUTH_TOKEN>" }
    }
  }
}
```

Если заголовок `Authorization` не задан, Zed сам инициирует стандартный OAuth-флоу
MCP — для нашего сервера, который OAuth не поддерживает, это даст ошибку.

## Проверка

**Settings → AI → MCP Servers** — точка-индикатор рядом с именем сервера:
зелёная и «Server is active» = подключено.

## Оговорки

- Ключ конфигурации — `context_servers`, а не `mcpServers` или `servers`.
- Поддержка удалённых серверов в Zed молодая; есть открытые проблемы с OAuth
  ([#43162](https://github.com/zed-industries/zed/issues/43162)) и remote ACP
  ([#52254](https://github.com/zed-industries/zed/issues/52254)).
- Сброс залипшей авторизации моста: `rm -rf ~/.mcp-auth`.

Источники: [zed.dev/docs/ai/mcp](https://zed.dev/docs/ai/mcp),
[geelen/mcp-remote](https://github.com/geelen/mcp-remote) (проверено 19.08.2026).
