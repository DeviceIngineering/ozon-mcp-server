# Cline (расширение VS Code)

**SSE:** поддерживается напрямую как legacy-транспорт, мост не нужен.

## Файл конфигурации

Документация Cline предлагает открывать файл через интерфейс и путь официально не
публикует. Фактическое расположение (**официально не подтверждено**):

| ОС | Путь |
|----|------|
| macOS | `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` |
| Linux | `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` |
| Windows | `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json` |

Для VS Code Insiders / Cursor / Windsurf сегмент `Code` меняется на каталог
соответствующего приложения. Для Cline CLI путь другой и он документирован:
`~/.cline/mcp.json`.

Через интерфейс:
- иконка **MCP Servers** в верхней панели Cline → вкладка **Configure** →
  кнопка **Configure MCP Servers** (откроет JSON);
- либо вкладка **Remote Servers**: Server Name + Server URL + Transport Type →
  выбрать **SSE (Legacy)** → **Add Server**.

## Без токена

```json
{
  "mcpServers": {
    "ozon": {
      "type": "sse",
      "url": "http://localhost:8000/sse",
      "disabled": false,
      "autoApprove": [],
      "timeout": 30000
    }
  }
}
```

## С `MCP_AUTH_TOKEN`

```json
{
  "mcpServers": {
    "ozon": {
      "type": "sse",
      "url": "http://localhost:8000/sse",
      "headers": { "Authorization": "Bearer <MCP_AUTH_TOKEN>" },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Поля схемы: `type` (`streamableHttp` | `sse`), `url`, `headers`, `disabled`,
`autoApprove`, `timeout` (в миллисекундах).

## Проверка

В панели **MCP Servers** у сервера `ozon` должен появиться список инструментов
(151 штука). Официальная рекомендация — убедиться, что инструменты видны, и
выполнить один вызов. Там же есть кнопка перезапуска зависшего сервера.

## Оговорки

- Если поле `type` не указать, Cline по умолчанию считает сервер SSE — для нас
  это правильно, но лучше указать явно.
- Заголовки задаются только правкой JSON; поддержка ввода headers прямо во вкладке
  Remote Servers документацией не описана — **не подтверждено**.
- Конфиг лежит в globalStorage и общий для всех рабочих областей.
- При медленном старте сервера поднимите `timeout`.

Источники:
[Connecting to a remote server](https://docs.cline.bot/mcp/connecting-to-a-remote-server),
[Configuring MCP servers](https://docs.cline.bot/mcp/configuring-mcp-servers)
(проверено 19.08.2026).
