# Gemini CLI

**SSE:** поддерживается напрямую, мост не нужен.

Транспорт в Gemini CLI выбирается именем ключа: `command` → stdio,
`url` → SSE, `httpUrl` → Streamable HTTP. Отдельного поля `type` нет.

## Файлы конфигурации

| Область | Путь |
|---------|------|
| Пользователь (macOS, Linux) | `~/.gemini/settings.json` |
| Пользователь (Windows) | `%USERPROFILE%\.gemini\settings.json` |
| Проект | `<проект>/.gemini/settings.json` |

Графического интерфейса нет.

## Быстрый способ — одна команда

```bash
# без токена
gemini mcp add --transport sse ozon http://localhost:8000/sse

# с токеном
gemini mcp add --transport sse --header "Authorization: Bearer <MCP_AUTH_TOKEN>" \
  ozon http://localhost:8000/sse
```

Флаги `gemini mcp add`: `--transport sse|http`, `--header "Name: value"`
(можно повторять), `--timeout <ms>`, `-s, --scope user|project`, `--trust`.

## То же самое в JSON

Без токена:

```json
{
  "mcpServers": {
    "ozon": {
      "url": "http://localhost:8000/sse",
      "timeout": 30000
    }
  }
}
```

С `MCP_AUTH_TOKEN`:

```json
{
  "mcpServers": {
    "ozon": {
      "url": "http://localhost:8000/sse",
      "headers": {
        "Authorization": "Bearer <MCP_AUTH_TOKEN>"
      },
      "timeout": 30000
    }
  }
}
```

## Проверка

Команда `/mcp` внутри Gemini CLI — статус подключения, список инструментов
(должно быть 151), состояние discovery. Снаружи: `gemini mcp list`.

## Оговорки

- Нельзя задавать `url` и `httpUrl` одновременно для одного сервера.
- Если сервер ответит 401, Gemini CLI попытается запустить OAuth-флоу
  (детект по коду ответа). Наш сервер OAuth не умеет — кладите токен сразу в
  `headers`, чтобы до 401 не доходило.
- Таймаута по умолчанию может не хватить на холодный старт — задайте `timeout`.
- OAuth-токены, если они всё-таки появятся, лежат в `~/.gemini/mcp-oauth-tokens.json`.

Источники:
[gemini-cli MCP docs](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md),
[docs site](https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html)
(проверено 19.08.2026).
