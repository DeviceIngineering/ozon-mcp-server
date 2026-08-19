# Claude Desktop

**Коротко: напрямую по SSE — нет, через мост `mcp-remote` — да.** Подключение
рабочее, просто настраивается не URL-ом, а локальной командой.

Почему так. «Custom connectors» в Claude Desktop подключаются к удалённому
MCP-серверу **из облачной инфраструктуры Anthropic, а не с вашего компьютера** —
это прямо написано в справке Anthropic и касается всех клиентов Claude (веб,
десктоп, мобильные). То есть `localhost`, вписанный в коннектор, указывает не на
вашу машину. Записи вида `"type": "sse"` + `"url"` в `claude_desktop_config.json`
официальной документацией тоже не описаны.

Зато локальные stdio-серверы Claude Desktop запускает прекрасно — этим и
пользуемся: `mcp-remote` стартует на вашей машине как обычный stdio-сервер и уже
из неё ходит на `http://localhost:8000/sse`.

Требуется Node.js 18+.

## Файл конфигурации

| ОС | Путь |
|----|------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | официального клиента Claude Desktop для Linux нет (документация упоминает только macOS и Windows) |

Через интерфейс: меню **Claude** в системной строке меню (не в окне) →
**Settings… → Developer → Edit Config**.

## Конфигурация — без токена

```json
{
  "mcpServers": {
    "ozon": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "http://localhost:8000/sse",
        "--transport", "sse-only"
      ]
    }
  }
}
```

## Конфигурация — с `MCP_AUTH_TOKEN`

```json
{
  "mcpServers": {
    "ozon": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "http://localhost:8000/sse",
        "--transport", "sse-only",
        "--header", "Authorization:${AUTH_HEADER}"
      ],
      "env": {
        "AUTH_HEADER": "Bearer <MCP_AUTH_TOKEN>"
      }
    }
  }
}
```

Почему заголовок разбит на две части: на Windows (Claude Desktop) и в Cursor есть
баг с экранированием пробелов внутри `args`, поэтому README `mcp-remote`
рекомендует передавать `Authorization:${AUTH_HEADER}` без пробела, а «Bearer …»
класть в `env`. На macOS этот вариант тоже работает.

Флаги:
- `--transport sse-only` — не пробовать Streamable HTTP, сразу SSE (наш сервер
  умеет только SSE). По умолчанию `mcp-remote` идёт `http-first`.
- `--allow-http` — разрешает соединение без TLS. Для `http://localhost` и
  `http://127.0.0.1` он **не нужен** (мост пропускает их сам), а вот для сервера
  на другой машине (`http://192.168.1.50:8000/sse`) — обязателен. Авторы
  `mcp-remote` просят применять его только в доверенной приватной сети.

Сервер на другой машине — замените `localhost` на её адрес и добавьте `--allow-http`.

## Проверка

1. Полностью перезапустите Claude Desktop (выход из приложения, не закрытие окна).
2. В поле ввода — **Add files, connectors, and more → Connectors → Manage connectors**:
   должен появиться `ozon` и список его инструментов.
3. Логи, если что-то не так:
   - macOS: `tail -n 50 -f ~/Library/Logs/Claude/mcp*.log`
   - Windows: `%APPDATA%\Claude\logs`

## Оговорки

- Пункт **Settings → Connectors → Add custom connector** для нашего сервера не
  подходит: он ожидает публичный URL, доступный из интернета, и умеет только OAuth,
  произвольных заголовков там нет.
- Сам `mcp-remote` авторы называют экспериментальным proof-of-concept.
- Залипшую авторизацию моста лечит `rm -rf ~/.mcp-auth`.

Источники:
[support.claude.com — custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp),
[modelcontextprotocol.io — connect local servers](https://modelcontextprotocol.io/docs/2026-07-28/develop/connect-local-servers),
[geelen/mcp-remote](https://github.com/geelen/mcp-remote) (проверено 19.08.2026).
