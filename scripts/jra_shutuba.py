"""JRA公式の出馬表を取って、展開図用の「結果の無いレース行」(races.jsonl と同じ形)にする。

    python3 scripts/jra_shutuba.py --date 2026-11-14
→ data/jra/shutuba_YYYYMMDD.jsonl  (result は着順なし。horse_id・馬番・枠・騎手・斤量・性齢・父・母の父)
出馬表の上 → 開催日(pw01drl…) → レース(pw01dde…)。3秒間隔。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

URL = "https://www.jra.go.jp/JRADB/accessD.html"
PLACE = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京", "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}
S = requests.Session()
S.headers["User-Agent"] = "nankeiba-research/0.1 (personal use)"
LAST = [0.0]


def post(c):
    w = 3.0 - (time.time() - LAST[0])
    if w > 0:
        time.sleep(w)
    LAST[0] = time.time()
    r = S.post(URL, data={"cname": c}, timeout=30)
    r.raise_for_status()
    return r.content.decode("shift_jis", errors="replace")


def txt(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def parse(html, cname):
    m = re.match(r"pw01dde\d{2}(\d{2})(\d{4})(\d{2})(\d{2})(\d{2})(\d{8})/", cname)
    jyo, year, kai, nichi, r, ymd = m.groups()
    body = txt(html)
    dist = re.search(r"コース：\s*([\d,]+)\s*メートル\s*（(芝|ダート|障害)", body)
    t = re.search(r"発走時刻：\s*(\d+)時(\d+)分", body)
    name = re.search(r'<span class="race_name">(.*?)</span>', html, re.S)
    cls = re.findall(r'<div class="cell (class|category)">(.*?)</div>', html, re.S)
    tb = re.search(r"<table[^>]*>(.*?)</table>", html, re.S).group(1)
    res = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S)[1:]:
        num = re.search(r'<td class="num"[^>]*>(.*?)</td>', tr, re.S)
        hid = re.search(r"pw01dud\d{2}(\d{10})/", tr)
        if not num or not hid or not txt(num.group(1)).isdigit():
            continue
        wk = re.search(r'alt="枠(\d)', tr)
        jk = txt(re.search(r'<td class="jockey"[^>]*>(.*?)</td>', tr, re.S).group(1))
        jm = re.match(r"(\S+)/\S+\s+([\d.]+)\s*kg\s+(.+)", jk)
        nm = txt(re.search(r'<div class="name">(.*?)</div>', tr, re.S).group(1))
        sire = re.search(r'<li class="sire"><span>父：</span>(.*?)</li>', tr, re.S)
        bms = re.search(r"母の父：(.*?)\)", txt(tr))
        res.append({"finish_pos": None, "umaban": int(txt(num.group(1))), "waku": int(wk.group(1)) if wk else None,
                    "horse_id": hid.group(1), "horse_name": nm, "sex_age": jm.group(1) if jm else None,
                    "kinryo": float(jm.group(2)) if jm else None,
                    "jockey": (jm.group(3) if jm else jk).replace(" ", "").replace("▲", "").replace("△", "").replace("☆", "").replace("◇", "").replace("★", "") if False else re.sub(r"\d+[A-Z]?$", "", (jm.group(3) if jm else jk).replace(" ", "")).translate(str.maketrans("", "", "▲△☆◇★")),
                    "sire": txt(sire.group(1)) if sire else None, "damsire": bms.group(1).strip() if bms else None,
                    "corner_pos": [], "time": None, "agari": None, "popularity": None})
    s = dist.group(2) if dist else None
    return {"race_id": f"{year}{jyo}{kai}{nichi}{r}", "date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}", "place": PLACE[jyo],
            "name": txt(name.group(1)) if name else "", "distance": int(dist.group(1).replace(",", "")) if dist else 0,
            "surface": "障" if "障害" in body[:3000] and "ジャンプ" in (txt(name.group(1)) if name else "") else {"芝": "芝", "ダート": "ダ", "障害": "障"}.get(s), "baba": None, "field_size": len(res),
            "result": sorted(res, key=lambda x: x["umaban"]), "lap": [], "corners": {}, "payouts": {},
            "race_class": txt(cls[1][1]) if len(cls) > 1 else None, "race_type": txt(cls[0][1]) if cls else None,
            "grade": None, "start": f"{int(t.group(1)):02d}:{t.group(2)}" if t else None, "source": "jra.go.jp shutuba"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    a = ap.parse_args()
    ymd = a.date.replace("-", "")
    top = post("pw01dli00/F3")
    days = sorted(set(c for c in re.findall(r"(pw01drl\d+/[0-9A-F]{2})", top) if ymd in c))
    out = Path(__file__).resolve().parents[1] / "data" / "jra" / f"shutuba_{ymd}.jsonl"
    with out.open("w", encoding="utf-8") as fo:
        for d in days:
            races = sorted(set(re.findall(r"(pw01dde\d+/[0-9A-F]{2})", post(d))))
            races = [c for c in races if c[-11:-3] == ymd]
            for c in races:
                row = parse(post(c), c)
                fo.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(row["place"], row["race_id"][-2:], row["surface"], row["distance"], row["field_size"], row["name"], flush=True)
    print("→", out)


if __name__ == "__main__":
    main()
