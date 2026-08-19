# Continue.dev

**SSE:** поддерживается напрямую (`type: sse`), мост не нужен.

Важное ограничение из документации: MCP работает **только в режиме agent**.

## Файлы конфигурации

| Область | Путь |
|---------|------|
| Глобально (macOS, Linux) | `~/.continue/config.yaml` |
| Глобально (Windows) | `%USERPROFILE%\.continue\config.yaml` |
| Отдельный сервер в проекте | `.continue/mcpServers/<имя>.yaml` в корне рабочей области |

Старый формат `config.json` с `experimental.modelContextProtocolServers` считается
устаревшим — для SSE используйте YAML.

Через интерфейс: выпадающий список конфигураций в IDE → шестерёнка рядом с
**Local Config** → откроется `config.yaml`. Отдельной формы «добавить MCP-сервер»
документация не описывает.

## Без токена

```yaml
mcpServers:
  - name: Ozon MCP
    type: sse
    url: http://localhost:8000/sse
```

## С `MCP_AUTH_TOKEN`

Вариант из официальных примеров Continue (поле `apiKey` — так токен передаётся в
примерах Linear, PostHog, Supabase):

```yaml
mcpServers:
  - name: Ozon MCP
    type: sse
    url: http://localhost:8000/sse
    apiKey: ${{ secrets.OZON_MCP_TOKEN }}
```

Точная форма заголовка, который Continue строит из `apiKey`, в документации
**не описана** — если сервер отвечает 401, используйте явные заголовки через
`requestOptions` (в справочнике `config.yaml` сказано, что `requestOptions` —
«optional HTTP settings for `sse` and `streamable-http` servers», а формат тот же,
что у `requestOptions` моделей, где есть `headers`; готового примера с headers
именно для MCP в документации нет, поэтому синтаксис ниже — **экстраполяция схемы,
примером не подтверждён**):

```yaml
mcpServers:
  - name: Ozon MCP
    type: sse
    url: http://localhost:8000/sse
    connectionTimeout: 10000
    requestOptions:
      headers:
        Authorization: Bearer <MCP_AUTH_TOKEN>
```

Гарантированно работающий запасной путь — токен в query-параметре, сервер его
понимает: `url: http://localhost:8000/sse?token=<MCP_AUTH_TOKEN>`.

## Проверка

Отдельного индикатора подключения документация не описывает. Переключитесь в
**Agent mode** и проверьте, что в списке инструментов появились `ozon_*`.

## Оговорки

- `mcpServers` здесь **список** (`- name: ...`), а не объект — в отличие от
  VS Code и Cline. Частая ошибка при копировании чужих конфигов.
- MCP доступен только в agent mode.
- Секреты — через `${{ secrets.NAME }}`.
- `connectionTimeout` управляет таймаутом первичного подключения.

Источники:
[MCP deep dive](https://docs.continue.dev/customize/deep-dives/mcp),
[MCP examples](https://docs.continue.dev/customize/deep-dives/mcp-examples),
[config.yaml reference](https://docs.continue.dev/reference) (проверено 19.08.2026).
