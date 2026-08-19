# Windsurf (ныне Devin Desktop)

**SSE:** поддерживается напрямую, мост не нужен.

⚠️ Продукт переименован: `docs.windsurf.com/windsurf/cascade/mcp` редиректит на
`docs.devin.ai/desktop/cascade/mcp`. Конфигурация зависит от того, каким агентом
вы пользуетесь: **legacy Cascade** (классический Windsurf) или **Devin Local agent**
(агент по умолчанию в новых вкладках). Ниже — оба варианта.

---

## Вариант 1. Legacy Cascade (классический Windsurf)

### Файл конфигурации

| ОС | Путь |
|----|------|
| macOS, Linux | `~/.codeium/windsurf/mcp_config.json` |
| Windows | по аналогии `%USERPROFILE%\.codeium\windsurf\mcp_config.json` — **в официальной документации путь для Windows не указан** |

Через интерфейс: иконка **`MCPs`** в правом верхнем углу панели Cascade, либо
**Settings → Cascade → MCP Servers**.

### Без токена

```json
{
  "mcpServers": {
    "ozon": {
      "serverUrl": "http://localhost:8000/sse"
    }
  }
}
```

### С `MCP_AUTH_TOKEN`

```json
{
  "mcpServers": {
    "ozon": {
      "serverUrl": "http://localhost:8000/sse",
      "headers": {
        "Authorization": "Bearer ${env:OZON_MCP_TOKEN}"
      }
    }
  }
}
```

Подстановка `${env:VAR}` и `${file:/path/to/file}` работает в полях `command`,
`args`, `env`, `serverUrl`, `url`, `headers`. Если переменная не задана —
подставится пустая строка.

Отдельного поля `type`/`transport` в Cascade нет: транспорт определяется URL,
поэтому адрес должен заканчиваться на `/sse`.

---

## Вариант 2. Devin Local agent (агент по умолчанию)

### Файлы конфигурации

| Область | Путь |
|---------|------|
| Пользователь (macOS, Linux) | `~/.config/devin/mcp_config.json` |
| Пользователь (Windows) | `%APPDATA%\devin\mcp_config.json` |
| Проект | `.devin/mcp_config.json` |
| Локально (в .gitignore, скоуп по умолчанию) | `.devin/mcp_config.local.json` |

Расположение изменилось в версии v3000.3.

### Конфигурация

```json
{
  "mcpServers": {
    "ozon": {
      "url": "http://localhost:8000/sse",
      "transport": "sse",
      "headers": {
        "Authorization": "Bearer ${env:OZON_MCP_TOKEN}"
      }
    }
  }
}
```

Без токена — уберите блок `headers`.

Поле `"transport": "sse"` здесь обязательно: по умолчанию Devin пробует
Streamable HTTP и откатывается на SSE **по тому же URL**, а у нас SSE живёт на
отдельном пути `/sse`. Документация описывает ровно этот случай.

Через CLI: `devin mcp add ozon --url http://localhost:8000/sse` (скоуп `-s project|user`),
заголовок затем дописать в файл руками.

### Оговорки

- `oauthClientId`/`oauthClientSecret` — не для статического токена; Bearer-токен
  передавайте только через `headers`.
- Корпоративным пользователям MCP может быть выключен администратором; в командах
  есть allowlist по Server ID, который регистрозависимо сверяется с ключом в конфиге.

---

## Проверка (оба варианта)

Панель **MCPs** → сервер `ozon` и список его инструментов (151 штука).
Отдельных индикаторов статуса и путей к логам в текущей документации нет.

Источники:
[docs.devin.ai/desktop/cascade/mcp](https://docs.devin.ai/desktop/cascade/mcp),
[docs.devin.ai/cli/extensibility/mcp/configuration](https://docs.devin.ai/cli/extensibility/mcp/configuration)
(проверено 19.08.2026).
