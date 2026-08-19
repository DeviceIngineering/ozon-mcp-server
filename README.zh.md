[Русский](README.md) · [English](README.en.md) · 中文

# Ozon MCP Server

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![MCP tools](https://img.shields.io/badge/MCP%20tools-151-orange.svg)](#功能一览)

在与 AI 助手的对话中直接打理你的 Ozon 店铺：价格、促销、广告、订单、退货、评价、
财务——基于 Ozon Seller API 与 Performance API 的 151 个工具（Ozon 是俄罗斯最大的
电商平台；Seller API 负责商品与经营，Performance API 负责付费广告）。
专为**经营多家店铺**的卖家设计：每次调用都带 `shop_id`，API 密钥加密保存在你自己的
服务器上，不会外传。
与其他 Ozon MCP 服务器的区别：除 Seller API 外还覆盖广告，并且内置诊断会在 AI 助手
撞上问题之前，先告诉你 Ozon 的哪些接口出了故障。

这是作者自用的生产工具：他每天在用，需要时才更新。具体含义见
[更新与支持](#更新与支持)。

> `docs/` 里各客户端的安装说明目前**只有俄语版**。不过其中的配置都是可直接粘贴的
> JSON，不依赖语言即可看懂：配置文件路径、地址 `http://localhost:8000/sse`，以及
> 请求头 `Authorization: Bearer <MCP_AUTH_TOKEN>`。

![Ozon MCP Server 仪表盘](docs/img/dashboard.png)

## 功能一览

| 分组 | 工具数 | 具体内容 |
|------|--------|----------|
| 促销与折扣 | 14 | Ozon 官方促销（列表、候选商品、加入/退出）、卖家自建促销、买家的「我要折扣」申请 |
| 价格与定价策略 | 14 | 设置售价与最低价、价格指数、最低价计时器、跟踪竞品的自动定价策略 |
| 广告（Performance API） | 22 | Trafarety（Ozon 的推荐位 CPC 广告）投放、出价与预算、Pay-per-order（按成交订单付费，CPO）、按商品与按日统计 |
| 商品 | 21 | 商品列表与详情、属性、库存、导入与批量更新、图片视频、归档、证书 |
| FBS 与 FBO 订单 | 17 | 待处理订单、发货打包（v4）、面单、取消、交接单、原产国 |
| 退货与取消 | 10 | FBO+FBS 统一退货列表、需卖家裁定的 rFBS 退货申请、订单取消申请 |
| 评价、提问、聊天 | 13 | 评价与回复、买家提问、买家聊天会话（v3） |
| 仓库与报表 | 8 | FBS 仓库、配送方式、报表生成与下载 |
| 财务 | 7 | 余额、交易明细、计提、销售实现报表、往来结算、现金流 |
| 类目、品牌、证书 | 7 | 类目树、类目属性及其可选值、证书 |
| 数据分析 | 5 | 按 SKU 的分析、库存与周转、商品在 Ozon 搜索中的排名、热门搜索词 |
| FBO 备货 | 4 | 备货申请单（v3）、状态计数、预约时段 |
| 店铺评分 | 2 | 当前卖家评分及其历史 |
| 诊断 | 2 | Ozon API 可用性自检、接口劣化探测 |
| 通知 | 2 | push webhook 订阅与事件类型字典 |
| 公司信息 | 2 | 卖家主体资料与费率 |
| 店铺 | 1 | 已接入店铺列表及其 `shop_id` |

FBO 与 FBS 是 Ozon 的两种履约模式：FBO 由 Ozon 仓库发货，FBS 由卖家自己的仓库发货，
rFBS 则是卖家自行配送的 FBS。

完整的工具名称列表见 `ozon_mcp/server.py` 中的 `TOOLS` 常量，或用任意 MCP 客户端
调用 `tools/list` 查看。

## 快速开始

需要 Docker。五条命令：

```bash
git clone https://github.com/DeviceIngineering/ozon-mcp-server.git
cd ozon-mcp-server
cp .env.example .env               # 内网使用可原样保留
docker compose up -d --build       # 构建镜像并在 8000 端口启动
open http://localhost:8000/shops   # 添加店铺与 Ozon 密钥
```

每一步都在做什么：

- `.env`——所有变量都是可选的。店铺密钥在网页界面里填写更方便，不必写在这里。
  如果服务不止你一个人能访问到，唯一值得先设置的是 `MCP_AUTH_TOKEN`
  （生成方式：`openssl rand -hex 32`）。
- `docker compose up -d --build`——按 `Dockerfile` 构建镜像，映射 `8000:8000` 端口，
  并创建 `ozon_data` 数据卷存放店铺、密钥、调用统计和诊断历史。
  `restart: unless-stopped` 会在机器重启后自动拉起容器。
- `/shops`——添加店铺的表单：`shop_id`（请用拉丁字母，之后在对话里就用它指代店铺）、
  店铺名称、Seller API 的 Client-Id + Api-Key，以及 Performance API 的
  Client-Id + Client-Secret。「Проверить」（测试）按钮会向 Ozon 发一次真实请求，
  告诉你密钥是否可用。

启动之后：

| 地址 | 用途 |
|------|------|
| `http://localhost:8000/` | 仪表盘：调用次数、错误、接口劣化 |
| `http://localhost:8000/shops` | 店铺与密钥 |
| `http://localhost:8000/diagnostics` | Ozon API 诊断 |
| `http://localhost:8000/api/health` | 健康检查接口，返回 JSON |
| `http://localhost:8000/sse` | **MCP 接入地址**，客户端填的就是它 |

请注意，网页界面是俄语的。

### 不使用 Docker

```bash
pip install .
DATA_DIR=./data PORT=8000 ozon-mcp-web
```

`DATA_DIR` 默认是 `/data`，本地直接运行时务必改成一个你有写权限的目录。

## 接入各客户端

传输方式为 SSE，地址 `http://<host>:8000/sse`。各客户端对 SSE 的支持不一样：有的可以
直连，有的需要 `mcp-remote` 中转。每个客户端都有单独的说明文件，含 macOS、Linux、
Windows 下的配置文件路径和可直接复制的 JSON——**目前只有俄语版**，但其中的 JSON 与
语言无关：

| 客户端 | 是否直连 SSE | 说明文件 |
|--------|--------------|----------|
| Claude Code | 是 | [docs/install-claude-code.md](docs/install-claude-code.md) |
| Claude Desktop | 否，需 `mcp-remote` 中转 | [docs/install-claude-desktop.md](docs/install-claude-desktop.md) |
| Cursor | 是 | [docs/install-cursor.md](docs/install-cursor.md) |
| Windsurf / Devin Desktop | 是 | [docs/install-windsurf.md](docs/install-windsurf.md) |
| VS Code（GitHub Copilot） | 是 | [docs/install-vscode-copilot.md](docs/install-vscode-copilot.md) |
| Cline | 是 | [docs/install-cline.md](docs/install-cline.md) |
| Continue.dev | 是 | [docs/install-continue.md](docs/install-continue.md) |
| Zed | 未经证实，建议用中转 | [docs/install-zed.md](docs/install-zed.md) |
| JetBrains AI Assistant / Junie | 是 | [docs/install-jetbrains.md](docs/install-jetbrains.md) |
| Gemini CLI | 是 | [docs/install-gemini-cli.md](docs/install-gemini-cli.md) |
| OpenAI Codex CLI | 否，需 `mcp-remote` 中转 | [docs/install-codex.md](docs/install-codex.md) |

最短的例子是 Claude Code：

```bash
claude mcp add --transport sse ozon http://localhost:8000/sse \
  --header "Authorization: Bearer <MCP_AUTH_TOKEN>"
```

客户端汇总表和中转工具说明见 [docs/README.md](docs/README.md)。

## 多店铺与安全

店铺数量不限。每个工具都有必填参数 `shop_id`，可用 `ozon_list_shops` 查询有哪些店铺。
在对话里就是这样用：「看一下 `alpha` 店的库存」。

![店铺页面](docs/img/shops.png)

密钥是怎么保存的：

- 首次使用时会在 `DATA_DIR` 下生成 `.encryption_key`，即 Fernet 密钥；
- 店铺密钥用它加密后存放在 `DATA_DIR/shops.json`；
- 网页界面里密钥以掩码显示（`abc***xyz`），保存掩码值不会覆盖真实密钥；
- 在 Docker 下这些都在 `ozon_data` 数据卷里。迁移到别的机器时要整卷拷贝，否则加密
  密钥会丢失（见 [DEPLOY.md](DEPLOY.md)，俄语）。

关于访问控制，需要知道：

- `MCP_AUTH_TOKEN` **只**保护 `/sse`。令牌通过 `Authorization: Bearer …` 请求头传递，
  也可以用 `?token=…` 查询参数。
- `MCP_AUTH_TOKEN` 为空即等于关闭鉴权，只有在可信网络里才可以这么做。
- 网页界面（`/`、`/shops`、`/diagnostics`）和 `/api/*` **不受令牌保护**：任何能访问到
  该端口的人都能看到仪表盘，并且能添加店铺。
- 不要把 8000 端口直接暴露到公网。需要远程访问请用 Tailscale 或 VPN。

## 实现原理

一个 Docker 容器，里面是一个 FastAPI 应用，同时充当 MCP 服务器和网页界面。

- **`ozon_mcp/server.py`**——MCP 服务器本体。`TOOLS` 列表描述全部 151 个工具（名称、
  说明、参数的 JSON schema），`call_tool` 处理器把调用路由到对应的 Ozon 客户端方法。
  客户端按 `shop_id` 放在连接池里，因此切换店铺不会重新建连。
- **`ozon_mcp/client.py`**——两个 HTTP 客户端：`OzonSellerClient`（`Client-Id` /
  `Api-Key` 请求头）和 `OzonPerformanceClient`（`client_credentials` 令牌，有效期
  30 分钟，会自动续期）。
- **`ozon_mcp/app.py`**——FastAPI：基于 `SseServerTransport` 的 `/sse` 接口、Bearer
  令牌校验、仪表盘/店铺/诊断三个页面，以及后台健康检查任务。
- **`ozon_mcp/settings.py`**——店铺与密钥：Fernet 加密、界面掩码、把环境变量里的密钥
  识别为名为 `default` 的店铺，以及把旧的单店铺 `settings.json` 迁移成 `shops.json`。
- **`ozon_mcp/diagnostics.py`**——探针：ping Ozon 的主机，外加对 Seller API 的 12 个
  类别各发一个开销很小的真实请求，并检查 Performance API 密钥。
- **`ozon_mcp/stats.py`**——通过 `aiosqlite` 使用 SQLite：记录每次工具调用的耗时与结果、
  健康检查历史，并据此计算接口劣化。

一些不那么直观的地方：

- Ozon 的广告出价和预算单位是**微卢布**：`1000000` = 1 ₽。看到七位数不用惊讶。
- 评价和提问接口返回 `403` 不是故障，而是没有 Premium Plus 订阅。诊断不会把这类响应
  算作错误。
- Ozon 的密钥本身不带有效期，只能从探针里的 `401` 判断密钥已失效。
- 广告的异步统计报表：同一时间只能有一个报表，最多 10 个广告计划、最长 62 天；工具最多
  等待约 2 分钟直到报表生成。
- 备货申请单在 API v3 里的状态是 1–8 的整数，不是字符串。

## 诊断

![诊断页面](docs/img/diagnostics.png)

*（截图里是一个使用了无效密钥的演示店铺，所以所有探针都是红的）*

- `/diagnostics` 页面：按店铺显示主机可达性、Seller API 的 12 项类别探测、
  Performance API 密钥检查，以及历次检查记录。
- 后台每 `HEALTH_CHECK_INTERVAL_MIN` 分钟自动检查一次（默认 30，设为 `0` 关闭）。
- 劣化探测：某个工具原本正常、现在持续失败，仪表盘就会提示「Ozon 可能改了 API」。
- 在对话里用 `ozon_diagnostics` 和 `ozon_degradations` 两个工具。
- 立即执行检查：页面上的按钮，或 `POST /api/diagnostics/run`。

## 环境变量

| 变量 | 默认值 | 作用 |
|------|--------|------|
| `MCP_AUTH_TOKEN` | 空 | `/sse` 的 Bearer 令牌。留空即不鉴权 |
| `HEALTH_CHECK_INTERVAL_MIN` | `30` | 后台诊断间隔（分钟），`0` 表示关闭 |
| `PORT` | `8000` | HTTP 服务端口 |
| `DATA_DIR` | `/data` | 存放 `shops.json`、`stats.db`、`.encryption_key` 的目录 |
| `OZON_CLIENT_ID`、`OZON_API_KEY` | 空 | `default` 店铺的 Seller API 密钥，适合不想在界面里录入的情况 |
| `OZON_PERF_CLIENT_ID`、`OZON_PERF_CLIENT_SECRET` | 空 | 同上，对应 Performance API |

## 已知的 Ozon API 限制（截至 2026 年 6 月）

- 广告：通过 API 只能创建 Trafarety（CPC）计划；预算和出价以微卢布计；官方没有查询
  广告账户余额的方法。
- Pay-per-order：自 2025 年 2 月起出价固定，只能开启或关闭。
- 评价、提问以及部分数据分析需要 Premium Plus 订阅（错误码 7）。
- `ozon_analytics` 中的转化漏斗指标已被 Ozon 标记为废弃——查搜索排名请用
  `ozon_product_queries`。
- `/v3/finance/transaction/*` 将于 2026-07-06 停用；替代方案已内置
  （`ozon_finance_cash_flow`、`ozon_finance_accruals`）。
- `ozon_product_stocks_by_warehouse` 使用 v2，因为 v1 将于 2026-04-07 停用。
- FBS 电子交接单已被 Ozon 于 2026-03-22 移除，改用普通交接单。
- Ozon API 没有「修改评价回复」的方法：只能删除原回复后重新发布。

## 2.0 版本的变化

对照 2026 年 6 月的 Ozon API 做了一轮彻底梳理，并逐个发真实请求核对过，而不是只看文档：
统一退货列表、取消 v2、销售实现 v2、ship v4、supply-order v3、真正可用的定价策略与
「我要折扣」、卖家自建促销、新的广告模型（Trafarety CPC + Pay-per-order）、诊断与劣化
探测，以及 MCP 接口的鉴权。

## 项目结构

```
ozon-mcp-server/
├── docker-compose.yml   # 8000 端口，ozon_data 数据卷
├── Dockerfile           # python:3.12-slim, uvicorn
├── DEPLOY.md            # 部署到独立机器、迁移数据
├── docs/                # 各客户端接入说明
└── ozon_mcp/
    ├── server.py        # MCP 服务器：151 个工具，多店铺
    ├── client.py        # Seller API + Performance API
    ├── app.py           # FastAPI：SSE、网页、鉴权、健康检查循环
    ├── diagnostics.py   # 类别探针、劣化探测
    ├── settings.py      # 店铺与密钥（Fernet）
    ├── stats.py         # 调用统计与检查历史（SQLite）
    └── templates/       # dashboard、diagnostics、shops
```

部署到独立机器以及迁移店铺数据见 [DEPLOY.md](DEPLOY.md)（俄语）。

## 更新与支持

Ozon 一直在改 API：接口会新增、改名、下线（上面的限制一节列的就是目前已经踩到的）。
这个服务器是作者自用的生产工具，**他自己需要时才更新**——也就是某次改动弄坏了他自己
店铺的功能的时候。好处是这份代码每天都在真实业务里被验证，而不是发布完就没人管了；
代价是没有发布计划，也不承诺响应时限。

如果你急需某项修复，请发邮件到 **d0371153@gmail.com**。
也欢迎提 issue 和 pull request，它们都会被认真看。

## 许可证

MIT——见 [LICENSE](LICENSE)。
