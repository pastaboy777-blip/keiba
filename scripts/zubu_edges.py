# -*- coding: utf-8 -*-
"""オッズ未開放の日に、各馬のエッジ集合＋399下地＋先行指数を一覧する（ズブ穴用）。

ana_recall.edges_for（穴ファクター）と ana399.evaluate（勝ち圏の上がり再現力）に
先行指数（senkou_index）を足して並べる。

399は「後方から勝ち圏の上がりを再現できるか」を測るので、前で粘って数字を出す馬は
構造的に0近くに出る。ズブ穴の本体はそちら側にいるため、先行指数を別軸で持つ。
大井84鞍942頭の実測では、今日4角1〜2番手を取れた馬の3着内率62%に対し、
取れなかった馬は16%だった。位置が取れるかどうかが単独で最大の分岐になる。

    python3 scripts/zubu_edges.py --date 2026-07-29 --place 川崎 --from 1 --to 5
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from pace_day import parse_laps

import ana_recall as R
import ana399 as A

CARD_URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"
PERF_URL = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{race_id}"

_DAY_CACHE: dict = {}


def prev_lap_index(client, ymd: str, place: str) -> dict:
    """前走日の全レースを走査し {馬名: 11秒台ラップ本数} を返す（『前走ハイレベル』判定用）。

    ラップは出馬表からは引けないため、前走当日の結果ページをまとめて読む。
    1日ぶん読めば同日の全馬に効くので、日単位でキャッシュする。
    """
    key = (ymd, place)
    if key in _DAY_CACHE:
        return _DAY_CACHE[key]
    idx: dict = {}
    try:
        html = client.get(CARD_URL.format(race_id=day_index_race_id(ymd, place)))
        races = dict(P.parse_race_links(html, date_yyyymmdd=ymd, jyo_code=ALL_CODES[place]))
    except Exception:
        races = {}
    for rid in races.values():
        try:
            rh = client.get(PERF_URL.format(race_id=rid))
        except Exception:
            continue
        laps = parse_laps(rh)
        if not laps:
            continue
        # 1本目が半端ハロン(50m等)だとスケールが壊れるので除外して数える
        eff = [t for t in laps if t >= 10.0] if laps[0] < 10.0 else laps
        c11 = sum(1 for t in eff if t < 12.0)
        for row in P.parse_result_page(rh, rid).rows:
            idx[row.horse_name] = c11
    _DAY_CACHE[key] = idx
    return idx


def _wakumap(n: int) -> dict:
    """頭数から馬番→枠番。外側の枠から2頭ずつ埋まる南関の割り振り。"""
    base, rem = n // 8, n % 8
    sizes = [base] * 8
    for i in range(rem):
        sizes[7 - i] += 1
    m, u = {}, 1
    for w in range(1, 9):
        for _ in range(sizes[w - 1]):
            if u <= n:
                m[u] = w
                u += 1
    return m


def _last_corners(e, k: int = 3) -> list:
    """近k走の4角通過順。取れないものは落とす。"""
    out = []
    for p in (e.recent_runs or [])[:k]:
        c = p.corner or []
        if c:
            out.append(c[-1])
    return out


def _lead_rivals(ents) -> int:
    """その鞍で『前走4角1番手』だった馬の頭数。少ないほど楽にハナを取れる。"""
    n = 0
    for e in ents:
        pc = _last_corners(e, 1)
        if pc and pc[0] == 1:
            n += 1
    return n


def senkou_index(e, dist: int, ents, wm: dict, rivals: int):
    """先行指数（0〜10）。『今日4角1〜2番手を取れるか』を事前情報だけで見る。

    大井84鞍942頭で測った実測値を重みの根拠にしている：
      前走4角1番手        → 今日4角1〜2番手 38%（全体20%）
      近3走の4角平均2.5以内 → 45%
      その鞍で前走ハナが自分だけ → 70%（2頭以上いると12〜38%まで落ちる）
      1〜3枠            → 53%（4枠より外は30%）
      距離延長           → 27%（同距離21%・短縮16%）
    そして前を取れた馬の3着内率は62%、取れなかった馬は16%。
    399（後ろから勝ち圏の上がりを再現する力）とは別方向を見る指標。
    """
    s, why = 0, []
    pc = _last_corners(e, 3)
    if pc and pc[0] == 1:
        s += 3
        why.append("前走ハナ")
    elif pc and any(v <= 2 for v in pc):
        s += 2
        why.append("近走ハナ2番手")
    if pc:
        m = sum(pc) / len(pc)
        if m <= 2.5:
            s += 2
            why.append("4角平均2.5以内")
        elif m <= 4:
            s += 1
            why.append("4角平均4以内")
    if pc and pc[0] == 1:
        if rivals <= 1:
            s += 3
            why.append("前走ハナは自分だけ")
        elif rivals == 2:
            s += 1
            why.append("前走ハナ2頭")
    w = e.waku or wm.get(e.umaban)
    if w and w <= 3:
        s += 1
        why.append("内枠")
    p0 = (e.recent_runs or [None])[0]
    if p0 and p0.distance and dist:
        d = dist - p0.distance
        if 0 < d <= 300:
            s += 1
            why.append("延長")
        elif d < 0:
            s -= 1
            why.append("短縮")
    return max(s, 0), why


def zubu_rank(ents, k: int = 3):
    """近k走の上がり最速で鞍内の順位を付ける。遅い側＝ズブい。{馬番: (順位, 母数)}"""
    vals = []
    for e in ents:
        ag = [p.agari for p in (e.recent_runs or [])[:k] if p.agari]
        if ag and e.umaban is not None:
            vals.append((min(ag), e.umaban))
    vals.sort()
    return {u: (i + 1, len(vals)) for i, (v, u) in enumerate(vals)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", default="川崎")
    ap.add_argument("--from", dest="r_from", type=int, default=1)
    ap.add_argument("--to", dest="r_to", type=int, default=12)
    ap.add_argument("--thr", type=float, default=40.5)
    ap.add_argument("--no-prev-lap", action="store_true",
                    help="前走ハイレベル判定をやめる(前走日の走査を省いて高速化)")
    args = ap.parse_args()

    pa, ba = A.load_adj()
    client = PoliteClient(use_cache=False)
    ymd = date.fromisoformat(args.date).strftime("%Y%m%d")
    html = client.get(CARD_URL.format(race_id=day_index_race_id(ymd, args.place)))
    races = dict(P.parse_race_links(html, date_yyyymmdd=ymd,
                                    jyo_code=NANKAN_CODES[args.place]))
    today = date.fromisoformat(args.date)

    for r in range(args.r_from, args.r_to + 1):
        if r not in races:
            continue
        page = P.parse_card_page(client.get(CARD_URL.format(race_id=races[r])), races[r])
        ents = getattr(page, "entries", page)
        tb = A.band(page.distance)
        print(f"=== {r}R ダ{page.distance} {len(ents)}頭")
        wm = _wakumap(len(ents))
        rivals = _lead_rivals(ents)
        zr = zubu_rank(ents)
        rows = []
        for e in ents:
            c11 = None
            if not args.no_prev_lap:
                pr0 = e.recent_runs[0] if e.recent_runs else None
                if pr0 and pr0.date and pr0.place in ALL_CODES:
                    c11 = prev_lap_index(client, pr0.date.replace("-", ""),
                                         pr0.place).get(e.horse_name)
            tags, cw = R.edges_for(e, page.distance, today=today, prev_c11=c11)
            ev = A.evaluate(e, tb, args.place, pa, ba, args.thr, False)
            si, swhy = senkou_index(e, page.distance, ents, wm, rivals)
            rk, tot = zr.get(e.umaban, (None, 0))
            # ズブい＝近走の終いが鞍内で遅い側。前を取れる見込みと重なった馬が本命候補。
            zubu = bool(rk and tot >= 6 and rk > tot / 2)
            rows.append((len(tags), ev["score"], e, tags, ev, cw, si, swhy, zubu, rk, tot))
        print(f"  ＊この鞍で前走4角1番手だった馬 {rivals}頭")
        for n, sc, e, tags, ev, bw, si, swhy, zubu, rk, tot in sorted(
                rows, key=lambda x: (-x[6], -x[0], -x[1])):
            um = f"{e.umaban:>2}" if e.umaban is not None else " ?"
            mark = "◇" if (si >= 5 and zubu) else " "
            ag = f"{rk}/{tot}" if rk else "-"
            print(f" {mark}{um} {e.horse_name:<12} 先行{si:<2} エッジ{n} 399={sc:4.1f} "
                  f"本物{ev['n_real']} 終い{ag:>5} 体重{bw or '-'} | {'・'.join(sorted(tags))}")
            if swhy:
                print(f"       先行の内訳: {'・'.join(swhy)}")
        print("  ◇ = 先行5以上 かつ 終いが鞍内で遅い側（前で残すズブい馬）")
        print()


if __name__ == "__main__":
    main()
