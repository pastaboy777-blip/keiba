"""川崎 2026-06-15 後半(9〜12R)の「ズブ穴」予想を実結果で検証する。

zubuana_kawasaki_0615.py が選んだズブ穴候補・本線を、楽天競馬の競走成績
(着順・三連複/三連単払戻)と突き合わせ、3着内的中・本線軸の着順・
三連複の捕捉可否をまとめる。

実行: python3 scripts/verify_zubuana_0615.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from nankeiba.ingest import rakuten
import zubuana_kawasaki_0615 as zb

CACHE = ROOT / "data" / "cache" / "rakuten"
BASE_ID = zb.BASE_ID
RACES = zb.RACES


def load_result(race_no: int) -> str:
    cached = CACHE / f"kawasaki_2026-06-15_{race_no}R_result.html"
    if cached.exists():
        return cached.read_text(encoding="utf-8", errors="replace")
    import urllib.request
    rid = rakuten.race_id(BASE_ID, race_no)
    req = urllib.request.Request(rakuten.race_result_url(rid),
                                 headers={"User-Agent": "Mozilla/5.0 (nankeiba)"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8")
    return text


def main() -> None:
    print("川崎 2026-06-15 後半 ズブ穴 × 実結果 検証\n")
    n_board = n_axis_board = 0
    n_picks = n_races = 0
    for rno in RACES:
        card = rakuten.parse_race_card(zb.load_page(rno))
        cand, order = zb.zubu_candidates(card)
        res = rakuten.parse_result(load_result(rno))
        finish = res["finish"]
        pos = {um: f for f, um, *_ in finish}        # 馬番 -> 着順
        top3 = {um for f, um, *_ in finish if f <= 3}
        names = {h["umaban"]: h["name"] for h in card["horses"]}

        n_races += 1
        picks = cand[:4]
        honsen = cand[0] if cand else None

        print("=" * 64)
        order_str = " ".join(f"{f}着{um}{nm}" for f, um, nm, *_ in finish[:3])
        print(f"川崎 {card['race_no']}R  結果: {order_str}")
        if res["trio"]:
            print(f"  三連複 {res['trio'][0]} {res['trio'][1]:,}円 / "
                  f"三連単 {res['trifecta'][0]} {res['trifecta'][1]:,}円")
        print("  ズブ穴 → 着順:")
        for r in picks:
            n_picks += 1
            p = pos.get(r["um"])
            hit = "★3着内" if r["um"] in top3 else ""
            if r["um"] in top3:
                n_board += 1
            ps = f"{p}着" if p else "圏外"
            head = "本線" if honsen and r["um"] == honsen["um"] else "  "
            print(f"    {head} {r['um']:2d} {names.get(r['um'], r['name']):<13s}"
                  f"単{r['odds']}/{r['pop']}人 → {ps} {hit}")
        if honsen:
            hp = pos.get(honsen["um"])
            if honsen["um"] in top3:
                n_axis_board += 1
            print(f"  本線軸 {honsen['um']}{names.get(honsen['um'], honsen['name'])}: "
                  f"{(str(hp)+'着') if hp else '圏外'}")
        # 三連複を「軸ズブ穴 + 相手order[:6]」で捕捉できたか
        if honsen and res["trio"]:
            partners = [u for u in order[:6] if u != honsen["um"]][:5]
            buy = set([honsen["um"]] + partners)
            hit3 = top3 and top3.issubset(buy)
            print(f"  三連複捕捉(軸{honsen['um']}-相手{partners}): "
                  f"{'的中' if hit3 else '不的中'}")
        print()

    print("=" * 64)
    print(f"集計: ズブ穴候補 {n_picks}頭中 3着内 {n_board}頭 / "
          f"本線軸の3着内 {n_axis_board}/{n_races}R")


if __name__ == "__main__":
    main()
