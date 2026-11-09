"""中央競馬の出馬表(馬柱)から展開予想を出す。

race.netkeiba.com の馬柱ページ(shutuba_past)に載っている近5走だけを使う。
レース当日以降の走は除外するので、レース後に実行しても結果は混ざらない。

使い方(要ネットワーク・requests):
    python3 scripts/jra_tenkai_card.py --race-id 202605050211 --date 2026-11-08
    # 保存済み HTML から(オフライン)
    python3 scripts/jra_tenkai_card.py --html past.html --date 2026-11-08 \
        --place 東京 --distance 2500 --surface 芝

注意:
- スコアは近走の着順ベースでクラス(G1/3勝クラス等)を補正しない。
  格上挑戦・格下げの馬は評価がずれる。展開(ペース・隊列・展開利)を主に見ること。
- 海外・地方の走は通過順が取れないことがある(その走は脚質推定に使われない)。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.core.interval import RunRecord
from nankeiba.core.features import RaceContext, horse_score
from nankeiba.core import tenkai as tk
from nankeiba.core import probability as pb
from nankeiba.scraping.race_id import place_of

PAST_URL = "https://race.netkeiba.com/race/shutuba_past.html?race_id={race_id}"


def _clean(cell: str) -> str:
    x = re.sub(r"<[^>]+>", " | ", cell).replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", x)


def parse_past_card(html: str, race_date: str):
    """馬柱 HTML → (馬番→馬名, 馬番→過去走[新しい順], レース条件文字列)。"""
    names: dict[int, str] = {}
    field: dict[int, list[RunRecord]] = {}
    for tr in re.findall(r'<tr class="HorseList.*?</tr>', html, re.S):
        um = (re.search(r'<td class="Waku\d*[^"]*"[^>]*>.*?</td>\s*<td[^>]*>\s*(\d+)', tr, re.S)
              or re.search(r'class="Umaban[^"]*"[^>]*>\s*(\d+)', tr))
        h = re.search(r'/horse/\w+[^>]*>([^<]+)<', tr)
        if not um or not h:
            continue
        u = int(um.group(1))
        names[u] = h.group(1).strip()
        runs: list[RunRecord] = []
        for _, cell in re.findall(r'<td class="(Past[^"]*)"[^>]*>(.*?)</td>', tr, re.S):
            x = _clean(cell)
            d = re.search(r"(\d{4})\.(\d{2})\.(\d{2})\s*(\S+?)\s", x)
            if not d:
                continue
            date = f"{d.group(1)}-{d.group(2)}-{d.group(3)}"
            if date >= race_date:
                continue  # 当日以降(=結果)は使わない
            fin = re.search(r"\|\s*(\d+)\s*\|", x[d.end():])
            cs_ = re.search(r"(芝|ダ|障)(\d{3,4})", x)
            fs = re.search(r"(\d+)頭", x)
            if not (fin and cs_ and fs):
                continue
            corner = re.search(r"\|\s*([\d\-]+)\s+\(\d", x)
            baba = re.search(r"\|\s*(良|稍|重|不)\s*\|", x)
            runs.append(RunRecord(
                date=date, place=re.sub(r"\d", "", d.group(4)),
                distance=int(cs_.group(2)), field_size=int(fs.group(1)),
                finish_pos=int(fin.group(1)), surface=cs_.group(1),
                baba=baba.group(1) if baba else None,
                corner_pos=[int(c) for c in corner.group(1).split("-")] if corner else [],
            ))
        runs.sort(key=lambda r: r.date, reverse=True)
        field[u] = runs
    m = re.search(r'class="RaceData01">(.*?)</div>', html, re.S)
    info = _clean(m.group(1)) if m else ""
    return names, field, info


def main() -> None:
    ap = argparse.ArgumentParser(description="中央競馬 出馬表から展開予想")
    ap.add_argument("--race-id")
    ap.add_argument("--html", help="保存済みの馬柱 HTML")
    ap.add_argument("--date", required=True, help="開催日 YYYY-MM-DD(これ以降の走は除外)")
    ap.add_argument("--place")
    ap.add_argument("--distance", type=int)
    ap.add_argument("--surface", choices=["芝", "ダ"])
    ap.add_argument("--baba", default=None)
    args = ap.parse_args()

    if args.html:
        html = Path(args.html).read_text(encoding="utf-8", errors="replace")
    elif args.race_id:
        from nankeiba.scraping.client import PoliteClient
        html = PoliteClient().get(PAST_URL.format(race_id=args.race_id))
    else:
        ap.error("--race-id か --html を指定してください")

    names, field, info = parse_past_card(html, args.date)
    place = args.place or (place_of(args.race_id) if args.race_id else None) or "東京"
    m = re.search(r"(芝|ダ)(\d{3,4})m", info)
    surface = args.surface or (m.group(1) if m else None)
    distance = args.distance or (int(m.group(2)) if m else 0)
    bm = re.search(r"(良|稍|重|不)", info)
    baba = args.baba or (bm.group(1) if bm else None)

    fc = tk.forecast(field, place=place, distance=distance, surface=surface)
    print(f"{place} {surface}{distance}m {baba or ''} {len(field)}頭")
    print(fc.summary())
    print("予想隊列(前→後): " + " → ".join(f"{u}{names[u]}" for u in fc.order))

    scores = {}
    for u, runs in field.items():
        ctx = RaceContext(args.date, place, distance, len(field), surface=surface,
                          baba=baba, tenkai_adv=fc.advantage[u])
        scores[u] = horse_score(runs, ctx)
    st = pb.strengths_from_scores(scores)
    print("\n 順 馬番 馬名             脚質  逃げ率 展開利  3着内率  近3走(着順/通過)")
    for i, u in enumerate(sorted(scores, key=scores.get, reverse=True), 1):
        s = fc.styles[u]
        recent = " ".join(
            f"{r.finish_pos}着({'-'.join(map(str, r.corner_pos)) or '—'})" for r in field[u][:3])
        print(f" {i:2d} {u:3d}  {names[u]:<12s} {s.style:<3s} {s.nige_rate:5.2f} "
              f"{fc.advantage[u]:+.3f}  {pb.top3_probability(st, u):5.1%}  {recent}")
    print("\n※スコアはクラス補正なし。展開(ペース・隊列・展開利)を主に参照のこと。")


if __name__ == "__main__":
    main()
