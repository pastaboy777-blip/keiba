"""トリップ定量化エンジン(プロトタイプ): 1レースの全頭を道中ロスで補正評価する。

着順は道中(流れ・位置・枠)に左右される。1レースの結果から各馬を:
  - レースの流れ(失速幅→前崩壊/前残り)と各馬の脚質(通過順)の相性
  - 枠ロス(外枠の距離損)
で補正し、『過小評価(次狙い)/過大評価(次危険)/真に強い』にタグ付けする。
中央(db.netkeiba・ラップ有)向け。stockしたレースを処理して"次走の宝"DBを作る土台。

実行例:
    python3 scripts/trip_adjust.py --race-id 202602010411
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from nankeiba.scraping import netkeiba as N
import lap33 as L33


def main():
    ap = argparse.ArgumentParser(description="トリップ補正評価(1レース)")
    ap.add_argument("--race-id", required=True)
    args = ap.parse_args()

    client = N.make_client(use_cache=True)
    html = L33.get_result_html(client, args.race_id)
    if not html:
        raise SystemExit("ラップ付き結果が取得できません(直近はdb未反映)")
    laps = N.parse_laps(html)
    res = N.parse_result(html)
    if not res or len(laps) < 4:
        raise SystemExit("データ不足")

    field = len(res)
    sh = round(laps[-2] - laps[-3], 2)                 # 失速幅
    flow = "前崩壊" if sh >= 1.5 else "前残り" if sh <= 0.7 else "中間"
    favored = "後" if flow == "前崩壊" else "前" if flow == "前残り" else None

    print(f"\n=== {N.place_of(args.race_id)} {int(args.race_id[10:12])}R トリップ補正評価 ===")
    print(f"失速幅 {sh:+.2f} → 流れ={flow}"
          f"{'(差し有利)' if flow=='前崩壊' else '(前有利)' if flow=='前残り' else ''}")
    print(f"{'着':>3}{'馬番':>4}{'枠':>3}{'人気':>4} {'馬名':<13}{'脚質':>5}{'トリップ':>8} 次走")

    out = []
    for r in res:
        lp = r.get("last_corner_pos")
        if not lp:
            continue
        ratio = (lp - 1) / (field - 1) if field > 1 else 0
        style = "前" if ratio <= 0.4 else "後" if ratio >= 0.6 else "中"
        hit = r["finish_pos"] <= 3
        # トリップスコア: + =不利だった(着順は過小) / − =恵まれた(過大)
        trip = 0.0
        if favored:
            if style != favored:
                trip += 1.0          # 流れ逆風=不利
            elif style == favored:
                trip -= 1.0          # 流れ向き=恵まれ
        # 枠ロス: 外枠(下数割)は距離損で僅かに不利
        if r.get("waku") and r["waku"] >= 7:
            trip += 0.3
        elif r.get("waku") and r["waku"] <= 2:
            trip -= 0.1
        # 位置損: 後方から着順を大きく上げた=強い動き(着順以上)
        gain = lp - r["finish_pos"]
        if gain >= field * 0.4:
            trip += 0.3

        # v2: 人気(市場の期待)を組み込み、着順vs人気のギャップがトリップで説明できる馬だけ拾う
        pop = r.get("popularity")
        bad = r["finish_pos"] >= max(6, field * 0.4)       # 明確に着外
        believed = pop is not None and pop <= field * 0.5  # 市場が期待していた(人気側)
        beat_market = pop is not None and (pop - r["finish_pos"]) >= 2  # 人気以上に走った

        if hit and trip >= 0.8 and (beat_market or (pop and pop >= 6)):
            stance = "◎◎真に強い(不利を覆し人気以上)"     # サムハンター型(最重要)
        elif bad and trip >= 0.8 and believed:
            stance = "◎次狙い(人気馬がトリップで凡走)"     # 次は人気薄化=妙味
        elif hit and trip <= -0.8 and not beat_market:
            stance = "▲次危険(流れ恵まれの好走)"
        else:
            stance = "中立"
        out.append((r["finish_pos"], r["umaban"], r.get("waku"), pop,
                    r["horse"], style, round(trip, 2), stance))

    for fp, um, wk, pop, nm, style, trip, stance in out:
        print(f"{fp:>3}{um:>4}{(wk or '?'):>3}{(pop or '?'):>4} {nm[:12]:<13}"
              f"{style:>5}{trip:>+8.2f} {stance}")
    print("\n◎次狙い=道中不利で着順が実力以下(次の妙味) / ▲次危険=流れ恵まれの好走(次は危険)")
    print("※トリップ定量化エンジン プロトタイプ。stock済みレースを処理して次走DB化する土台。")


if __name__ == "__main__":
    main()
