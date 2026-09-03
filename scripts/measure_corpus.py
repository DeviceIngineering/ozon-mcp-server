"""Замер того, сколько контекста стоят ответы инструментов, на корпусе живых ответов.

Корпус собирается scripts/collect_corpus.py и в репозиторий не коммитится:
это выгрузка реального кабинета. Здесь считается, что с ним делает shaping.shape.

    python scripts/measure_corpus.py ~/corpus

Без tiktoken считает символы, с ним — токены (cl100k, близко к токенайзеру Claude).
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from ozon_mcp import shaping  # noqa: E402

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    size = lambda text: len(_enc.encode(text))
    unit = "токенов"
except ImportError:
    size = len
    unit = "символов"

dumps = lambda data: json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


def main(corpus_dir: str) -> int:
    files = sorted(pathlib.Path(corpus_dir).glob("*.json"))
    if not files:
        print(f"В {corpus_dir} нет файлов корпуса")
        return 1

    rows, total_before, total_after = [], 0, 0
    for path in files:
        name = path.stem
        if name.startswith("_"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        before = size(dumps(data))
        shaped, notes = shaping.shape(name, {"limit": 50}, data)
        after = size(dumps(shaped)) + sum(size(n) for n in notes)
        rows.append((name, before, after, len(notes)))
        total_before += before
        total_after += after

    rows.sort(key=lambda r: r[1] - r[2], reverse=True)
    print(f"{'инструмент':32s} {'было':>9s} {'стало':>9s} {'дельта':>8s}  заметки")
    for name, before, after, notes in rows:
        delta = f"−{100 - after * 100 // before}%" if before else "—"
        print(f"{name:32s} {before:9d} {after:9d} {delta:>8s}  {notes}")
    saved = 100 - total_after * 100 // total_before if total_before else 0
    print(f"\nвсего {unit}: {total_before} → {total_after} (−{saved}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "corpus"))
