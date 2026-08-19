# VS Code (GitHub Copilot, agent mode)

**SSE:** поддерживается напрямую (`"type": "sse"`), мост не нужен.

## Способ 1 — одна команда в терминале

```bash
code --add-mcp '{"name":"ozon","type":"sse","url":"http://localhost:8000/sse","headers":{"Authorization":"Bearer <MCP_AUTH_TOKEN>"}}'
```

Без токена — уберите `headers`. Отдельной команды `code mcp add` нет, только этот
флаг.

Оговорка: в официальной документации у `--add-mcp` показан **только пример со
stdio-сервером** (`command` + `args`). Поля `type`, `url` и `headers` — из
официальной схемы `mcp.json`, так что форма выше корректна по схеме, но именно
таким примером в документации не проиллюстрирована. Если команда не сработает,
берите способ 2 — он документирован полностью.

## Способ 2 — файлы конфигурации

| Область | Путь |
|---------|------|
| Рабочая область | `.vscode/mcp.json` в корне проекта |
| Пользовательский уровень | `mcp.json` в папке профиля VS Code — открывается командой `MCP: Open User Configuration`. Точные пути в документации не приведены; фактически это `~/Library/Application Support/Code/User/mcp.json` (macOS), `~/.config/Code/User/mcp.json` (Linux), `%APPDATA%\Code\User\mcp.json` (Windows) — **официально не подтверждено** |

Через интерфейс: **Command Palette → `MCP: Add Server`** (мастер, выбор
Workspace/Global), список серверов — `MCP: List Servers`, поиск в Extensions по `@mcp`.

## Без токена

`.vscode/mcp.json`:

```json
{
  "servers": {
    "ozon": {
      "type": "sse",
      "url": "http://localhost:8000/sse"
    }
  }
}
```

## С `MCP_AUTH_TOKEN` — токен спрашивается при запуске (рекомендуется)

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "ozon-token",
      "description": "MCP_AUTH_TOKEN сервера Ozon MCP",
      "password": true
    }
  ],
  "servers": {
    "ozon": {
      "type": "sse",
      "url": "http://localhost:8000/sse",
      "headers": { "Authorization": "Bearer ${input:ozon-token}" }
    }
  }
}
```

Вариант с токеном прямо в файле (годится только для локального `mcp.json`,
не для того, что коммитится):

```json
{
  "servers": {
    "ozon": {
      "type": "sse",
      "url": "http://localhost:8000/sse",
      "headers": { "Authorization": "Bearer <MCP_AUTH_TOKEN>" }
    }
  }
}
```

## Проверка

- **Command Palette → `MCP: List Servers`** → выбрать `ozon` → **Show Output**:
  в логе видно подключение и ошибки.
- В Chat view → **Configure Tools**: должны появиться инструменты `ozon_*`.

## Оговорки

- Корневой ключ здесь `servers`, а **не** `mcpServers` — частая ошибка при
  копировании конфига из Claude Desktop или Cline.
- `"type": "http"` сначала пробует Streamable HTTP и только потом падает на SSE;
  для нашего `/sse` указывайте `"type": "sse"` сразу.
- Токен в открытом виде в `.vscode/mcp.json` попадёт в git — используйте `inputs`.
- Отдельно существует портируемый файл `~/.copilot/mcp-config.json` для Agent Host;
  он не читает `.vscode/mcp.json`.

Источники:
[MCP configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration),
[Use MCP servers](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
(проверено 19.08.2026).
