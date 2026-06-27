"""netkeiba(中央/JRA)の過去成績付き出馬表から、ズブ穴候補を脚質×枠で出す。

地方(笠松)で実証した「人気薄 × 脚質(前残り日は前/差し日は差し) × 内〜中枠」を中央へ移植。
南関学習のv2は中央へ転移しないため、転移に強い脚質(senkou)・枠・人気を主軸にする。
脚質は shutuba_past.html の各馬の近走『通過順』から算出(馬ごとのクロール不要)。

実行例:
    python3 scripts/nk_zubu.py --race-id 202602010511 --bias sashi --draw inner
    python3 scripts/nk_zubu.py --date 2026-06-27 --place 函館 --from 7 --bias front
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bs4 import BeautifulSoup

from nankeiba.scraping import netkeiba as N
from nankeiba.core import features as F
from nankeiba.core import interval as iv

PAST_URL = "https://race.netkeiba.com/race/shutuba_past.html?race_id={race_id}"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱"


def circ(n):
    return CIRCLED[n - 1] if isinstance(n, int) and 1 <= n <= len(CIRCLED) else str(n)


def _parse_past_cell(td):
    """1つの近走セルから (頭数, 最終コーナー位置, 着順) を取り出す。"""
    def txt(cls):
        d = td.find("div", class_=cls)
        return d.get_text(" ", strip=True) if d else ""
    # Data06: "9-11-14-15 (39.2) 492(-2)" → 通過順
    d06 = txt("Data06")
    corner = []
    m = re.match(r"\s*([\d-]+)", d06)
    if m and "-" in m.group(1):
        corner = [int(x) for x in m.group(1).split("-") if x.isdigit()]
    elif m and m.group(1).isdigit():
        corner = [int(m.group(1))]
    # Data03: "15頭 12番 11人 黛弘人 53.0" → 頭数
    d03 = txt("Data03")
    fm = re.search(r"(\d+)頭", d03)
    field = int(fm.group(1)) if fm else None
    # Data01 の span.Num = 着順
    num = td.find("span", class_="Num")
    fp = int(num.get_text(strip=True)) if num and num.get_text(strip=True).isdigit() else None
    return field, (corner[-1] if corner else None), fp, corner


def parse_past_table(html: str):
    """過去成績付き出馬表をパースして各馬の情報を返す。

    返り値: [{umaban, waku, horse, jockey, senkou, n_runs}] (馬番順)
    """
    soup = BeautifulSoup(html, "html.parser")
    t = soup.find("table", class_=re.compile("Shutuba_Past5"))
    if t is None:
        return []
    tb = t.find("tbody") or t
    cells = tb.find_all("td")
    horses = []
    cur = None
    for td in cells:
        classes = td.get("class") or []
        cls = " ".join(classes)
        if any(re.fullmatch(r"Waku[1-8]", c) for c in classes):  # 枠色セル=馬の区切り
            if cur:
                horses.append(cur)
            wk = re.search(r"\d+", td.get_text(strip=True))
            cur = {"waku": int(wk.group()) if wk else None, "umaban": None,
                   "pasts": [], "horse": None, "jockey": None}
        elif cur is None:
            continue
        elif "Waku" in classes:                # 馬番セル(classが厳密に Waku)
            um = re.search(r"\d+", td.get_text(strip=True))
            cur["umaban"] = int(um.group()) if um else None
        elif "Horse_Info" in cls:
            a = td.find("a", href=re.compile(r"/horse/"))
            cur["horse"] = a.get_text(strip=True) if a else td.get_text(" ", strip=True)[:12]
        elif "Jockey" in cls:
            # "牝4鹿 古川吉 53.0" → 斤量(末尾の数値)の直前トークンが騎手
            toks = td.get_text(" ", strip=True).split()
            wi = next((k for k in range(len(toks) - 1, -1, -1)
                       if re.fullmatch(r"\d+\.?\d*", toks[k])), len(toks))
            cur["jockey"] = toks[wi - 1] if wi - 1 >= 0 else (toks[-1] if toks else "?")
        elif "Past" in cls:
            cur["pasts"].append(_parse_past_cell(td))
    if cur:
        horses.append(cur)

    out = []
    for i, hdat in enumerate(horses, 1):
        recs = []
        for field, last, fp, corner in hdat["pasts"]:
            if field and corner:
                recs.append(iv.RunRecord(
                    date="2000-01-01", place="?", distance=0, field_size=field,
                    finish_pos=fp or 1, corner_pos=corner))
        senkou = F.senkou_power(recs) if recs else 0.0
        out.append({"umaban": hdat.get("umaban") or i, "waku": hdat["waku"],
                    "horse": hdat["horse"] or "?", "jockey": hdat["jockey"] or "?",
                    "senkou": senkou, "n_runs": len(recs)})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="netkeiba中央 ズブ穴(脚質×枠×人気薄)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--race-id", help="12桁レースID(単レース)")
    g.add_argument("--date", help="YYYY-MM-DD(その日を場指定で)")
    ap.add_argument("--place", help="場(--date時に必須相当): 東京/函館/小倉 等")
    ap.add_argument("--from", dest="from_r", type=int, default=1)
    ap.add_argument("--to", dest="to_r", type=int, default=12)
    ap.add_argument("--bias", choices=["front", "sashi"], default="sashi",
                    help="front=前残り日(前で運べる馬) / sashi=差し日(差し馬)。既定sashi")
    ap.add_argument("--draw", choices=["all", "inner"], default="all",
                    help="inner=内〜中枠(馬番が頭数の約6割以内)のみ")
    ap.add_argument("--pop-min", type=int, default=None,
                    help="人気薄しきい値(この人気以下のみ。単勝オッズAPIから人気取得)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    client = N.make_client(use_cache=not args.no_cache)
    if args.race_id:
        rids = [args.race_id]
    else:
        rids = N.race_ids_for_date(client, args.date.replace("-", ""))
        if args.place:
            rids = [r for r in rids if N.place_of(r) == args.place]
        rids = [r for r in rids if args.from_r <= int(r[10:12]) <= args.to_r]
    if not rids:
        raise SystemExit("対象レースが見つかりません。")

    for rid in rids:
        horses = parse_past_table(client.get(PAST_URL.format(race_id=rid)))
        if not horses:
            print(f"\n{N.place_of(rid)}{int(rid[10:12])}R: パース失敗")
            continue
        field = len(horses)
        thr = round(field * 0.6)
        pops = N.win_pop(client, rid) if args.pop_min else {}
        cands = horses
        if args.draw == "inner":
            cands = [h for h in cands if h["umaban"] <= thr]
        if args.pop_min and pops:
            cands = [h for h in cands if pops.get(h["umaban"], (0, 99))[1] >= args.pop_min]
        # 差し日=senkou昇順(差し優先) / 前残り日=senkou降順(前優先)
        cands = sorted(cands, key=lambda h: h["senkou"], reverse=(args.bias == "front"))
        tag = "差し優先" if args.bias == "sashi" else "前残り優先"
        dtag = "・内〜中枠" if args.draw == "inner" else ""
        ptag = f"・{args.pop_min}番人気↓" if args.pop_min else ""
        print(f"\n=== {N.place_of(rid)} {int(rid[10:12])}R ズブ穴({tag}{dtag}{ptag}) {field}頭 ===")
        for h in cands[:5]:
            style = ("逃げ" if h["senkou"] >= 0.35 else "先行" if h["senkou"] >= 0.1
                     else "差し" if h["senkou"] <= -0.1 else "中団")
            po = pops.get(h["umaban"])
            ptxt = f" {po[1]}人気({po[0]})" if po else ""
            print(f"  {circ(h['umaban'])}枠{h['waku']} {h['horse'][:10]:<10} "
                  f"{h['jockey'][:4]:<4} 脚質{h['senkou']:+.2f}({style}){ptxt} 近{h['n_runs']}走")


if __name__ == "__main__":
    main()
