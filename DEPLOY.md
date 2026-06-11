# Деплой Ozon MCP Server на отдельный Mac mini

Сервер — самодостаточный Docker-сервис. Все данные (магазины, токены, статистика,
история диагностики) живут в Docker-томе `ozon_data`.

## 1. Установка на новый Mac mini

Требования: Docker Desktop (или OrbStack).

```bash
# На старом маке: упаковать проект (без данных)
cd ~/Documents/myProjects/cowork/FBO
tar -czf ozon-mcp-server.tar.gz --exclude='.git' --exclude='__pycache__' ozon-mcp-server

# Передать на новый Mac mini
scp ozon-mcp-server.tar.gz user@<новый-мак>:~/

# На новом Mac mini:
tar -xzf ozon-mcp-server.tar.gz && cd ozon-mcp-server
cp .env.example .env
# Сгенерировать токен авторизации и вписать в .env → MCP_AUTH_TOKEN
openssl rand -hex 32

docker compose up -d --build
```

Проверка: `curl http://localhost:8000/api/health` → `{"status": "ok", ...}`

## 2. Перенос магазинов со старого сервера

Токены хранятся зашифрованными, ключ шифрования — в том же томе,
поэтому переносим том целиком:

```bash
# На старом маке:
docker run --rm -v ozon-mcp-server_ozon_data:/data -v $(pwd):/backup alpine \
  tar -czf /backup/ozon_data.tar.gz -C /data .
scp ozon_data.tar.gz user@<новый-мак>:~/ozon-mcp-server/

# На новом Mac mini (контейнер остановить на время восстановления):
docker compose down
docker run --rm -v ozon-mcp-server_ozon_data:/data -v $(pwd):/backup alpine \
  sh -c "cd /data && tar -xzf /backup/ozon_data.tar.gz"
docker compose up -d
```

Либо просто заново добавить магазины через веб-UI: `http://<новый-мак>:8000/shops`.

## 3. Автозапуск после перезагрузки Mac mini

`restart: unless-stopped` в docker-compose уже поднимает контейнер при старте
Docker. Остаётся включить автозапуск Docker Desktop:
**Docker Desktop → Settings → General → Start Docker Desktop when you sign in**.

Также в macOS: **Системные настройки → Пользователи → Объекты входа** — Docker должен быть в списке.

## 4. Подключение OpenClaw

OpenClaw подключается к MCP по SSE. В конфигурации MCP-серверов OpenClaw
(например `~/.openclaw/mcporter.json` или раздел `mcpServers`):

```json
{
  "mcpServers": {
    "ozon": {
      "type": "sse",
      "url": "http://<IP-мака-с-сервером>:8000/sse",
      "headers": {
        "Authorization": "Bearer <MCP_AUTH_TOKEN из .env>"
      }
    }
  }
}
```

Если клиент не умеет передавать заголовки — токен можно передать параметром:
`http://<IP>:8000/sse?token=<MCP_AUTH_TOKEN>`.

Подключение Claude Code с любой машины:

```bash
claude mcp add --transport sse ozon "http://<IP>:8000/sse" \
  --header "Authorization: Bearer <MCP_AUTH_TOKEN>"
```

## 5. Сеть и безопасность

- В локальной сети достаточно `MCP_AUTH_TOKEN` + статический IP/имя хоста
  (Mac mini: Системные настройки → Сеть → зафиксировать IP, либо использовать
  `<имя-мака>.local`).
- **Не пробрасывайте порт 8000 в интернет напрямую.** Для доступа извне —
  Tailscale (рекомендуется: `tailscale up`, адрес вида `100.x.y.z`) или VPN.
- Веб-дашборд (`/`, `/shops`, `/diagnostics`) не закрыт токеном — он доступен
  всем, кто имеет сетевой доступ к порту. В доверенной сети это ок.

## 6. Диагностика

| Что | Где |
|-----|-----|
| Здоровье сервиса + сводка | `GET /api/health` |
| Страница диагностики (ключи, хосты, пробы, деградации) | `http://<IP>:8000/diagnostics` |
| Запустить проверку сейчас | кнопка на странице или `POST /api/diagnostics/run` |
| Полная диагностика магазина (JSON) | `GET /api/diagnostics/<shop_id>` |
| Из Claude/OpenClaw | инструменты `ozon_diagnostics`, `ozon_degradations` |

Фоновая проверка выполняется каждые `HEALTH_CHECK_INTERVAL_MIN` минут (по умолчанию 30):
доступность хостов api-seller и api-performance + лёгкие реальные запросы по 12 категориям Seller API + проверка ключей Performance API.
Результаты видны на дашборде; деградации инструментов (работал → стабильно падает)
подсвечиваются как возможное изменение Ozon API.

## 7. Обновление

```bash
cd ~/ozon-mcp-server
# скопировать новые исходники поверх (или git pull, если репозиторий)
docker compose up -d --build
```

Данные в томе `ozon_data` при пересборке сохраняются.
