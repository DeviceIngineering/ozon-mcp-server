# JetBrains AI Assistant и Junie (IDEA, PyCharm и др.)

**SSE:** поддерживается напрямую. Но передача заголовка `Authorization`
в AI Assistant официально не документирована — если у вас задан `MCP_AUTH_TOKEN`,
надёжнее идти через мост `mcp-remote` (или через Junie, где `headers` описаны).

AI Assistant и Junie — **разные конфигурации MCP**: настройка в одном не
переносится в другой.

---

## AI Assistant

Справка JetBrains перечисляет три транспорта: STDIO, Streamable HTTP и
**SSE («for legacy MCP servers»)**. Доступно начиная с линейки 2026.1.

**Настройка:** **Settings | Tools | AI Assistant | Model Context Protocol (MCP)**
→ **Add** → вставить JSON → **Apply**.

Расположение файла на диске в официальной справке **не указано** (конфигурация
живёт в каталоге настроек IDE: `~/Library/Application Support/JetBrains/<IDE>/…`
на macOS, `~/.config/JetBrains/<IDE>/…` на Linux,
`%APPDATA%\JetBrains\<IDE>\…` на Windows; конкретное имя файла документацией
не названо) — настраивайте через интерфейс.

### Без токена

```json
{
  "mcpServers": {
    "ozon": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### С `MCP_AUTH_TOKEN`

Поля `headers` в справке JetBrains по MCP нет (запрос на OAuth/аутентификацию —
[LLM-25012](https://youtrack.jetbrains.com/issue/LLM-25012)). Два рабочих пути:

1. Токен в query-параметре — сервер это поддерживает:
   ```json
   {
     "mcpServers": {
       "ozon": { "url": "http://localhost:8000/sse?token=<MCP_AUTH_TOKEN>" }
     }
   }
   ```
2. Мост `mcp-remote` (нужен Node.js 18+):
   ```json
   {
     "mcpServers": {
       "ozon": {
         "command": "npx",
         "args": [
           "-y", "mcp-remote", "http://localhost:8000/sse",
           "--transport", "sse-only",
           "--header", "Authorization:${AUTH_HEADER}"
         ],
         "env": { "AUTH_HEADER": "Bearer <MCP_AUTH_TOKEN>" }
       }
     }
   }
   ```

### Проверка

В списке MCP-серверов появится колонка **Status**; клик по иконке в ней покажет
список доступных инструментов.

### Оговорки

- Поле `headers` в AI Assistant упоминается в блогах и сообществе, но в
  jetbrains.com/help его нет — **не подтверждено**, не полагайтесь на него вслепую.
- Если сервер отвечает 401, AI Assistant может показать лишний диалог регистрации
  OAuth-клиента.

---

## Junie

Junie поддерживает удалённые серверы с `url` и `headers`; поддержка SSE заявлена
начиная с версии плагина линейки `2xx.406.xx`
([JUNIE-461](https://youtrack.jetbrains.com/issue/JUNIE-461),
[JUNIE-536](https://youtrack.jetbrains.com/issue/JUNIE-536)).

### Файлы конфигурации (документированы официально)

| Область | Путь |
|---------|------|
| Проект | `<проект>/.junie/mcp/mcp.json` |
| Пользователь (macOS, Linux) | `~/.junie/mcp/mcp.json` |
| Пользователь (Windows) | `%USERPROFILE%\.junie\mcp\mcp.json` |

Через интерфейс: панель Junie → **MCP settings** → **Add** (откроет `mcp.json`).

### Конфигурация

```json
{
  "mcpServers": {
    "ozon": {
      "url": "http://localhost:8000/sse",
      "headers": { "Authorization": "Bearer <MCP_AUTH_TOKEN>" }
    }
  }
}
```

Без токена — уберите `headers`.

Нужно ли для SSE поле `"type": "sse"` — в документации Junie **не описано**;
документированный пример удалённого сервера идёт без `type`.

### Проверка

Список MCP Servers в настройках Junie со статусом подключения и списком
инструментов; в Junie CLI — команда `/mcp`.

### Оговорки

- Подстановка `${env:VAR}` в `headers` встречается в сторонних примерах, но
  документацией Junie **не подтверждена** — вписывайте токен строкой и не
  коммитьте `.junie/mcp/mcp.json`.

Источники:
[AI Assistant — MCP](https://www.jetbrains.com/help/ai-assistant/mcp.html),
[Configure an MCP server](https://www.jetbrains.com/help/ai-assistant/configure-an-mcp-server.html),
[Junie CLI MCP configuration](https://junie.jetbrains.com/docs/junie-cli-mcp-configuration.html),
[Junie plugin MCP settings](https://junie.jetbrains.com/docs/junie-plugin-mcp-settings.html)
(проверено 19.08.2026).
