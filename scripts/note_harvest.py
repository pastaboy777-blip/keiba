"""note.com のクリエイター記事を全部集める(一覧 → 本文)。止めても続きから。

    python3 scripts/note_harvest.py munehironet

一覧 … /api/v2/creators/<id>/contents?kind=note&page=N
本文 … /api/v3/notes/<key>  (有料記事は無料部分だけが返る)
→ data/note/<id>/list.jsonl, data/note/<id>/body.jsonl {"key","date","title","price","text"}
2秒間隔・1本ずつ。200以外は60秒あけて1回だけやり直し、だめなら止める。
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path

import requests

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (personal research)"
LAST = [0.0]


def get(url):
    w = 2.0 - (time.time() - LAST[0])
    if w > 0:
        time.sleep(w)
    LAST[0] = time.time()
    r = S.get(url, timeout=30)
    if r.status_code != 200:
        time.sleep(60)
        r = S.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def text_of(body: str) -> str:
    body = re.sub(r"<(br|/p|/h\d|/li|/figure|/blockquote)[^>]*>", "\n", body or "")
    return re.sub(r"\n{3,}", "\n\n", html.unescape(re.sub(r"<[^>]+>", "", body))).strip()


def main():
    cid = sys.argv[1]
    out = Path(__file__).resolve().parents[1] / "data" / "note" / cid
    out.mkdir(parents=True, exist_ok=True)
    lp, bp = out / "list.jsonl", out / "body.jsonl"
    items = {}
    if lp.exists():
        for l in open(lp):
            d = json.loads(l)
            items[d["key"]] = d
    page = 1
    with lp.open("a") as fo:
        while True:
            d = get(f"https://note.com/api/v2/creators/{cid}/contents?kind=note&page={page}")["data"]
            new = 0
            for c in d["contents"]:
                if c["key"] not in items:
                    items[c["key"]] = {"key": c["key"], "date": c["publishAt"], "title": c["name"],
                                       "price": c.get("price"), "can_read": c.get("canRead")}
                    fo.write(json.dumps(items[c["key"]], ensure_ascii=False) + "\n")
                    new += 1
            if d.get("isLastPage") or not d["contents"]:
                break
            page += 1
            if page % 10 == 0:
                print(f"一覧 {page}ページ {len(items)}本", flush=True)
    print(f"一覧 {len(items)}本", flush=True)
    done = {json.loads(l)["key"] for l in open(bp)} if bp.exists() else set()
    todo = [k for k in sorted(items, key=lambda k: items[k]["date"], reverse=True) if k not in done]
    with bp.open("a") as fo:
        for i, k in enumerate(todo, 1):
            n = get(f"https://note.com/api/v3/notes/{k}")["data"]
            rec = dict(items[k], text=text_of(n.get("body")), paid_part_hidden=bool(n.get("price")) and not n.get("is_purchased"))
            fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fo.flush()
            if i % 50 == 0:
                print(f"本文 {i}/{len(todo)}", flush=True)
    print("NOTE_DONE", flush=True)


if __name__ == "__main__":
    main()
