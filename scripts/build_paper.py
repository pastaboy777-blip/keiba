#!/usr/bin/env python3
"""実データから新聞(指数＆展開予想)を生成する。

入力は 1 レース分の JSON(出馬表＋各馬の過去走)。明日の大井などを自前で作るための
本番エントリポイント。

入力 JSON の形(entries.json):
{
  "header": {"place":"大井","distance":1600,"date":"2026-07-22","race_no":11,
             "baba":"良","post_time":"20:10","race_name":"○○特別(C1)"},
  "entries": [
    {"umaban":1,"name":"ウマА","sex_age":"牝3","jockey":"○○","trainer":"××",
     "history":[
        {"date":"2026-07-08","place":"大井","distance":1600,"field_size":12,
         "finish_pos":3,"baba":"良","corner_pos":[2,3,3,4],
         "time_sec":100.2,"last3f_sec":39.1},
        ... 新しい順に過去走 ...
     ]},
    ...
  ]
}

過去走の time_sec(走破タイム秒)があれば指数が付く。first3f_sec/last3f_sec/corner_pos
があるほど前3F・展開の精度が上がる。基準タイム・馬場差は入力内の全過去走から
自己校正する(--corpus で追加の学習用 JSONL を渡すと精度が上がる)。

    python3 scripts/build_paper.py entries.json --out out/oi_11r.html
    python3 scripts/build_paper.py entries.json --corpus data/results.jsonl --text

依存ライブラリなし(標準ライブラリのみ)。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core.interval import RunRecord                 # noqa: E402
from nankeiba.core.hindex import SpeedIndexModel             # noqa: E402
from nankeiba.core import newspaper as nb                    # noqa: E402


_RUN_FIELDS = {
    "date", "place", "distance", "field_size", "finish_pos", "jockey", "trainer",
    "popularity", "baba", "corner_pos", "agari_rank", "days_since_last",
    "time_sec", "first3f_sec", "last3f_sec",
}


def _run_from_dict(d: dict) -> RunRecord:
    kw = {k: v for k, v in d.items() if k in _RUN_FIELDS}
    kw.setdefault("field_size", 0)
    kw.setdefault("finish_pos", kw.get("field_size", 0) or 99)
    return RunRecord(**kw)


def load_entries(path: str):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    h = doc["header"]
    header = nb.RaceHeader(
        place=h["place"], distance=int(h["distance"]), date=h.get("date", ""),
        race_no=h.get("race_no"), baba=h.get("baba"),
        post_time=h.get("post_time"), race_name=h.get("race_name"),
    )
    entries = []
    for e in doc["entries"]:
        hist = [_run_from_dict(r) for r in e.get("history", [])]
        entries.append(nb.PaperEntry(
            umaban=int(e["umaban"]), name=e.get("name", str(e["umaban"])),
            history=hist, sex_age=e.get("sex_age"),
            jockey=e.get("jockey"), trainer=e.get("trainer"), waku=e.get("waku"),
        ))
    return header, entries


def load_corpus(path: str) -> list[RunRecord]:
    """学習用 JSONL(collect_data.py 形式の結果)から過去走を集める。"""
    runs: list[RunRecord] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            for r in d.get("result", []):
                rd = dict(r)
                rd.setdefault("date", d.get("date"))
                rd.setdefault("place", d.get("place"))
                rd.setdefault("distance", d.get("distance"))
                rd.setdefault("field_size", d.get("field_size", 0))
                runs.append(_run_from_dict(rd))
    return runs


def main():
    ap = argparse.ArgumentParser(description="実データから指数＆展開予想の新聞を生成")
    ap.add_argument("entries", help="1レース分の出馬表＋過去走 JSON")
    ap.add_argument("--corpus", help="指数校正用の追加 JSONL(任意)")
    ap.add_argument("--out", default="out/paper.html")
    ap.add_argument("--text", action="store_true", help="テキストも標準出力")
    ap.add_argument("--base", type=float, default=0.0, help="指数の基準値オフセット")
    args = ap.parse_args()

    header, entries = load_entries(args.entries)

    # 学習用の走: 入力の全過去走 + (あれば) corpus
    train = [r for e in entries for r in e.history]
    if args.corpus:
        train += load_corpus(args.corpus)
    model = SpeedIndexModel.fit(train, base=args.base)

    card = nb.build_card(header, entries, model)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(nb.render_html(card))
    print(f"HTML を書き出しました: {args.out}")

    if args.text:
        print()
        print(nb.render_text(card))


if __name__ == "__main__":
    main()
