"""「ズブい馬をいかに走らせるか」の各サインが、人気薄の3着内に効くか検証する。

コンセプトの核=陣営が手を尽くして今日走らせにきた馬を、市場の盲点で拾う。
その"走らせる行動"を個別に評価し、学習/検証の両期間で安定して効くものを特定する。

検証する『走らせる』サイン(いずれも人気薄=exp_pop>=6 に限定):
  - 乗り替わり強化   : 今走の騎手3着内率 > 前走騎手(=上位騎手を確保=走らせにきた)
  - 上位騎手騹乗     : 騎手3着内率が高い(連続値)
  - 叩き2-3走目     : 休み明けから2〜3走目(良化のピーク)
  - 連闘/詰め(≤14日) / 中1-2週(15-20日)
  - 距離短縮         : 前走より短い距離へ(忙しくして前で運ばせる)
  - 場替わり         : 競馬場を替えてきた(条件を合わせにきた)
  - 馬体重しぼり     : 馬体重が減(仕上げてきた) / 増
  - 交互作用         : 叩き2-3 × 上位騎手 / 短間隔 × タフネス高

各サインは「該当馬の3着内率 ÷ 全人気薄ベース」=リフトで評価。

実行: python3 scripts/analyze_hashiraseru.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import backtest_wet as bw
import predict_nankan as pn

POP_MIN = 6
CUTOFF = "2026-05-01"


def main() -> None:
    races = bw.load_races()
    jtable = pn.jockey_top3_from_samples(bw.FILES)  # 前走騎手の質を引くため

    def rows(pred_period):
        out = []
        for r in races:
            if not pred_period(r["date"]):
                continue
            for h in r["horses"]:
                if h.get("exp_pop") is None or h["exp_pop"] < POP_MIN:
                    continue
                if h.get("finish_pos") is None:
                    continue
                out.append((h, 1 if h["finish_pos"] <= 3 else 0))
        return out

    train = rows(lambda d: d < CUTOFF)
    test = rows(lambda d: d >= CUTOFF)

    def jq(h):
        v = h.get("jockey_top3_rate")
        return v if v else jtable.get(h.get("jockey"), 0.0)

    def upgraded(h):
        sig = h.get("signals") or {}
        if not sig.get("jockey_changed"):
            return False
        prev = jtable.get(sig.get("prev_jockey"), 0.0)
        return jq(h) - prev >= 3.0   # 3着内率で3pt以上の強化

    SIGNS = {
        "乗り替わり強化": lambda h: upgraded(h),
        "上位騎手(3着内≥22%)": lambda h: jq(h) >= 22,
        "叩き2-3走目": lambda h: (h.get("signals") or {}).get("tatakii_n") in (2, 3),
        "連闘/詰め(≤14日)": lambda h: (lambda d: d is not None and d <= 14)((h.get("signals") or {}).get("days_since_last")),
        "中1-2週(15-20日)": lambda h: (lambda d: d is not None and 15 <= d <= 20)((h.get("signals") or {}).get("days_since_last")),
        "距離短縮": lambda h: (lambda x: x is not None and x < 0)((h.get("signals") or {}).get("distance_change")),
        "場替わり": lambda h: bool((h.get("signals") or {}).get("place_changed")),
        "馬体重しぼり(減)": lambda h: (lambda w: w is not None and w < 0)((h.get("signals") or {}).get("weight_diff")),
        "タフネス高(≥0.6)": lambda h: (lambda t: t is not None and t >= 0.6)((h.get("signals") or {}).get("toughness")),
        "叩き2-3 × 上位騎手": lambda h: (h.get("signals") or {}).get("tatakii_n") in (2, 3) and jq(h) >= 22,
        "短間隔 × タフネス高": lambda h: (lambda s: s.get("days_since_last") is not None and s["days_since_last"] <= 20 and (s.get("toughness") or 0) >= 0.6)(h.get("signals") or {}),
    }

    def lift(data, pred):
        base = sum(y for _, y in data) / len(data)
        sub = [(h, y) for h, y in data if pred(h)]
        if len(sub) < 15:
            return None, len(sub), base
        rate = sum(y for _, y in sub) / len(sub)
        return rate / base, len(sub), rate

    btr = sum(y for _, y in train) / len(train)
    bte = sum(y for _, y in test) / len(test)
    print(f"人気薄(>={POP_MIN}) 学習{len(train)}(ベース{btr*100:.1f}%)/"
          f"検証{len(test)}(ベース{bte*100:.1f}%)\n")
    print(f"  {'走らせるサイン':<22}{'学習リフト(n)':>16}{'検証リフト(n)':>16}  判定")
    res = []
    for name, pred in SIGNS.items():
        ltr, ntr, _ = lift(train, pred)
        lte, nte, rte = lift(test, pred)
        res.append((name, ltr, ntr, lte, nte, rte))
    res.sort(key=lambda x: -(x[3] or 0))
    for name, ltr, ntr, lte, nte, rte in res:
        if ltr is None or lte is None:
            print(f"  {name:<22}{'(標本不足)':>16}")
            continue
        good = ltr > 1.05 and lte > 1.05
        verdict = "◎効く(安定)" if good else ("△片側のみ" if (ltr > 1.05 or lte > 1.05) else "×効かない")
        print(f"  {name:<22}{f'{ltr:.2f}x(n={ntr})':>16}{f'{lte:.2f}x(n={nte})':>16}  {verdict}")
    print("\n※ リフト>1=その『走らせる』行動をした人気薄が、平均より3着内に来やすい。")
    print("  両期間で>1.05が安定して効くサイン=ランキングの軸に据える候補。")


if __name__ == "__main__":
    main()
