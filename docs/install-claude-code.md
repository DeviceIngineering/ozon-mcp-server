# Claude Code (CLI)

**SSE:** поддерживается напрямую, мост не нужен.

## Файлы конфигурации

| ОС | Пользовательский / локальный скоуп | Проектный скоуп |
|----|-----------------------------------|-----------------|
| macOS | `~/.claude.json` | `.mcp.json` в корне проекта |
| Linux | `~/.claude.json` | `.mcp.json` в корне проекта |
| Windows | `%USERPROFILE%\.claude.json` | `.mcp.json` в корне проекта |

Графического интерфейса нет — внутри сессии есть слэш-команда `/mcp`.

## Быстрый способ — одна команда

Без токена (`MCP_AUTH_TOKEN` в `.env` пустой):

```bash
claude mcp add --transport sse ozon http://localhost:8000/sse
```

С токеном:

```bash
claude mcp add --transport sse ozon http://localhost:8000/sse \
  --header "Authorization: Bearer <MCP_AUTH_TOKEN>"
```

Сервер на другой машине — подставьте её адрес: `http://192.168.1.50:8000/sse`.

Скоуп задаётся флагом `--scope local|project|user` (по умолчанию `local`).

## То же самое в JSON

`.mcp.json` в корне проекта (или соответствующая секция `~/.claude.json`):

```json
{
  "mcpServers": {
    "ozon": {
      "type": "sse",
      "url": "http://localhost:8000/sse",
      "headers": {
        "Authorization": "Bearer ${OZON_MCP_TOKEN}"
      }
    }
  }
}
```

Подстановка переменных окружения (`${VAR}`, `${VAR:-default}`) в `.mcp.json`
поддерживается для полей `url`, `headers`, `command`, `args`, `env` — так токен
не попадёт в git. Без токена блок `headers` просто убирается.

## Проверка

```bash
claude mcp list          # ожидаем: ozon  ✔ Connected
claude mcp get ozon      # карточка сервера, строка Issue: при ошибке
```

Внутри сессии — `/mcp`: статус `connected` и число инструментов (должно быть 151).
Спросите у Claude: «покажи список магазинов Ozon» — он вызовет `ozon_list_shops`.

## Оговорки

- Запись с `url`, но без `type` Claude Code считает stdio-сервером и ругается:
  `has a "url" but no "type"`. Для нашего эндпоинта — всегда `"type": "sse"`.
- Если токен неверный, Claude Code помечает соединение как failed и **не**
  переходит на OAuth-флоу.
- Пробелы и переносы строк в значении заголовка не обрезаются — Claude Code
  предупреждает `Leading or trailing whitespace in: headers.Authorization`.
- Серверы из проектного `.mcp.json` требуют интерактивного подтверждения при
  первом запуске (`claude mcp reset-project-choices` — сбросить решение).
- Транспорт SSE в спецификации MCP помечен как устаревший в пользу Streamable
  HTTP; Claude Code его по-прежнему поддерживает, но пишет об этом в документации.

Источники: [code.claude.com/docs/en/mcp](https://code.claude.com/docs/en/mcp),
[quickstart](https://code.claude.com/docs/en/mcp-quickstart) (проверено 19.08.2026).
