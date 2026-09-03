"""Снимок реальных ответов инструментов — корпус для замеров контекста.

Запускается там, где есть доступ к кабинету (обычно внутри контейнера):

    docker cp scripts/collect_corpus.py ozon-mcp-server:/tmp/
    docker exec ozon-mcp-server python /tmp/collect_corpus.py --out /tmp/corpus
    docker cp ozon-mcp-server:/tmp/corpus ./corpus

Вызываются только читающие инструменты, без единой записи в кабинет.
ФИО, телефоны, почта, ИНН и идентификаторы кабинета маскируются ДО записи файла:
корпус — выгрузка живого магазина, в репозиторий он не коммитится (см. .gitignore).

Дальше корпус читает scripts/measure_corpus.py.
"""

import argparse
import asyncio
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

READ_ONLY = [
    "ozon_product_list", "ozon_get_prices", "ozon_actions_list", "ozon_finance_balance",
    "ozon_ad_campaigns", "ozon_ad_balance", "ozon_search_promo_products",
    "ozon_returns_fbo", "ozon_rating_summary", "ozon_stock_on_warehouses",
    "ozon_warehouse_list", "ozon_category_tree", "ozon_report_list",
    "ozon_discount_tasks", "ozon_product_limits", "ozon_supply_orders",
]
# лимиты Performance API: статистика считается асинхронно
THROTTLED = {"ozon_ad_statistics", "ozon_product_queries"}

PII_KEY = re.compile(r"(fio|name|phone|email|address|client|recipient|passport|inn|kpp|"
                     r"ogrn|account|card|contact|supplier|legal|seller)", re.I)
ID_KEY = re.compile(r"(sid|seller_?id|supplier_?id|shop_?id|client_?id|api_?key|token)", re.I)
PHONE = re.compile(r"\+?\d[\d\-\s()]{9,}\d")
EMAIL = re.compile(r"[\w.\-]+@[\w.\-]+\.\w+")


def mask(node, key_hint=""):
    if isinstance(node, dict):
        return {k: mask(v, k) for k, v in node.items()}
    if isinstance(node, list):
        return [mask(x, key_hint) for x in node]
    if isinstance(node, str):
        if PII_KEY.search(key_hint) or ID_KEY.search(key_hint):
            return "<masked:%s>" % hashlib.sha256(node.encode()).hexdigest()[:8]
        return EMAIL.sub("<email>", PHONE.sub("<phone>", node))
    return node


def arguments_for(schema, shop_id, limit):
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)
    props = schema.get("properties") or {}
    args = {"shop_id": shop_id}
    for key, value in (("date_from", week_ago), ("date_to", today),
                       ("start", week_ago), ("end", today), ("date", week_ago)):
        if key in props:
            args[key] = str(value)
    if "limit" in props:
        args["limit"] = limit
    return args


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="corpus")
    parser.add_argument("--limit", type=int, default=50, help="сколько записей просить у списков")
    parser.add_argument("--shop", help="shop_id; по умолчанию первый из настроенных")
    args = parser.parse_args()

    from ozon_mcp.server import TOOLS, call_tool
    from ozon_mcp.settings import load_shops

    shops = load_shops(pathlib.Path(os.environ.get("DATA_DIR", "/data")))
    if not shops:
        print("Нет ни одного магазина — нечего снимать")
        return 1
    shop_id = args.shop or sorted(shops)[0]

    schemas = {t.name: t.inputSchema for t in TOOLS}
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    for name in READ_ONLY:
        if name not in schemas:
            print(f"SKIP {name}: нет в TOOLS")
            continue
        try:
            blocks = await asyncio.wait_for(
                call_tool(name, arguments_for(schemas[name], shop_id, args.limit)), timeout=120)
            payload = json.loads(blocks[0].text)
        except Exception as exc:
            print(f"FAIL {name}: {type(exc).__name__}: {str(exc)[:80]}")
            continue
        (out_dir / f"{name}.json").write_text(
            json.dumps(mask(payload), ensure_ascii=False), encoding="utf-8")
        print(f"OK   {name}")
        saved += 1
        if name in THROTTLED:
            await asyncio.sleep(21)

    print(f"\nсохранено {saved} ответов в {out_dir} (ПДн замаскированы)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
