"""血統(父・母・母の父)を JRA公式から集める。2段階・止めても続きから。

    python3 scripts/jra_blood_harvest.py --data data/jra/races.jsonl

段階1 … 月 → 開催日 → レースの結果ページをたどり、出走馬の馬ページへのリンク(照合記号つき)を集める。
         対象は 新馬・未勝利の鞍と、クラスの記録が無い鞍(血統で補いたい、過去走の少ない馬が多いところ)。
         → data/jra/horse_links.jsonl  {"race_id", "horses": {horse_id: cname}}
段階2 … 集めた馬のページ(GET accessU.html?CNAME=…)から 父・母・母の父 を取る。
         → data/jra/pedigree.jsonl  {"horse_id", "name", "sire", "dam", "damsire"}
3秒間隔・1本ずつ。503 と接続切れは60秒あけて1回だけやり直し、それ以外の200以外で止める。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import jra_official_harvest as H  # noqa: E402
from nankeiba.scraping.jra_official import links, month_checksums, race_id_of  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "jra"


def horse_get(f: H.Fetcher, cname: str) -> str:
    import requests
    wait = f.sleep - (time.time() - f.last)
    if wait > 0:
        time.sleep(wait)
    f.last = time.time()
    url = "https://www.jra.go.jp/JRADB/accessU.html"
    try:
        r = f.s.get(url, params={"CNAME": cname}, timeout=30)
    except requests.exceptions.RequestException:
        time.sleep(60)
        r = f.s.get(url, params={"CNAME": cname}, timeout=30)
    if r.status_code == 503:
        time.sleep(60)
        r = f.s.get(url, params={"CNAME": cname}, timeout=30)
    if r.status_code != 200:
        raise H.Stop(f"HTTP {r.status_code}: {cname}")
    return r.content.decode("shift_jis", errors="replace")


def parse_pedigree(html: str) -> dict:
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))

    def grab(pat):
        m = re.search(pat, txt)
        return m.group(1).strip() if m else None
    return {"name": grab(r"競走馬情報 競走馬情報 (\S+)"),
            "sire": grab(r"プロフィール 父 (.+?) 性別"),
            "dam": grab(r"(?<!の)\s母 (.+?) (?:産駒|馬齢)"),
            "damsire": grab(r"母の父 (.+?) 生年月日"),
            "damdam": grab(r"母の母 (.+?) 毛色"),
            "birth": grab(r"生年月日 (\d{4}年\d{1,2}月\d{1,2}日)"),
            "origin": grab(r"産地 (\S+)")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA / "races.jsonl"))
    ap.add_argument("--from", dest="frm", default="2023-11")
    ap.add_argument("--to", default="2026-11")
    ap.add_argument("--sleep", type=float, default=3.0)
    ap.add_argument("--stage2-first", action="store_true", help="段階1を飛ばし、今あるリンクで段階2(新馬戦の馬から先)")
    a = ap.parse_args()
    target = set()
    for l in open(a.data, encoding="utf-8"):
        d = json.loads(l)
        c = (d.get("race_class") or "") + (d.get("name") or "")
        if d.get("surface") in ("芝", "ダ") and ("新馬" in c or "未勝利" in c or not d.get("race_class")):
            target.add(d["race_id"])
    links_path = DATA / "horse_links.jsonl"
    ped_path = DATA / "pedigree.jsonl"
    days_path = DATA / "blood.days"
    done_r = {json.loads(l)["race_id"] for l in open(links_path)} if links_path.exists() else set()
    done_d = set(days_path.read_text().split()) if days_path.exists() else set()
    print(f"段階1: 対象 {len(target)}鞍(済み {len(done_r)})", flush=True)
    f = H.Fetcher(a.sleep)
    try:
        # ---- 段階1 ----
        ck = {} if a.stage2_first else month_checksums(f.post(H.SEARCH))
        with links_path.open("a", encoding="utf-8") as fo, days_path.open("a") as fd:
            for y, m in ([] if a.stage2_first else H.months(a.frm, a.to)):
                key = f"{y % 100:02d}{m:02d}"
                if key not in ck:
                    continue
                prefix = "pw01skl00" if (y, m) >= (2026, 11) else "pw01skl10"
                for day in links(f.post(f"{prefix}{y:04d}{m:02d}/{ck[key]}"), "pw01srl"):
                    if day in done_d:
                        continue
                    for c in links(f.post(day), "pw01sde"):
                        rid = race_id_of(c)
                        if not rid or rid not in target or rid in done_r:
                            continue
                        html = f.post(c)
                        hs = dict(re.findall(r"CNAME=(pw01dud\d{2}(\d{10})/[0-9A-F]{2})", html))
                        hs = {hid: cn for cn, hid in re.findall(r"CNAME=(pw01dud\d{2}(\d{10})/[0-9A-F]{2})", html)}
                        fo.write(json.dumps({"race_id": rid, "horses": hs}, ensure_ascii=False) + "\n")
                        fo.flush()
                        done_r.add(rid)
                    fd.write(day + "\n")
                    fd.flush()
                print(f"{y}-{m:02d} 済み (累計 {len(done_r)}鞍)", flush=True)
        # ---- 段階2 ----
        horses, debut = {}, set()
        cls = {}
        for l in open(a.data, encoding="utf-8"):
            d = json.loads(l)
            cls[d["race_id"]] = (d.get("race_class") or "") + (d.get("name") or "")
        for l in open(links_path, encoding="utf-8"):
            d = json.loads(l)
            horses.update(d["horses"])
            if "新馬" in cls.get(d["race_id"], "") or "デビュー" in cls.get(d["race_id"], ""):
                debut.update(d["horses"])
        done_h = {json.loads(l)["horse_id"] for l in open(ped_path)} if ped_path.exists() else set()
        todo = sorted((h for h in horses if h not in done_h), key=lambda h: (h not in debut, -int(h)))   # 新馬戦の馬・若い馬から
        print(f"段階2: 馬 {len(horses)}頭(済み {len(done_h)}、残り {len(todo)})", flush=True)
        with ped_path.open("a", encoding="utf-8") as fo:
            for i, hid in enumerate(todo, 1):
                p = parse_pedigree(horse_get(f, horses[hid]))
                p["horse_id"] = hid
                fo.write(json.dumps(p, ensure_ascii=False) + "\n")
                fo.flush()
                if i % 200 == 0:
                    print(f"  馬 {i}/{len(todo)}", flush=True)
        print("BLOOD_DONE", flush=True)
    except H.Stop as e:
        print(f"止めました: {e}", flush=True)


if __name__ == "__main__":
    main()
