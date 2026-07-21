#!/usr/bin/env python3
"""
paddock_predict.py — 新聞の指数 × 当日の気配スコア → 総合予想

新聞の指数(近走の能力の下地)と、パドック歩様から出した気配スコア(当日の気配)を
合成して、全頭を総合スコアでランキングする。指数だけ／気配だけでも動く。

考え方:
  総合 = w_指数 × 指数(正規化) + w_気配 × 気配(正規化)
  ・指数 = 能力の下地（新聞。高いほど良い。負値でも可＝相対で正規化）
  ・気配 = 当日のパドックの動き（歩様。高いほど良い）

使い方:
    # 指数だけでランキング（気配はまだ無い場合）
    python paddock_predict.py --shisu shisu.csv

    # 指数 × 気配 を合成（既定 指数60% 気配40%）
    python paddock_predict.py --shisu shisu.csv --kehai field_gait_compare.csv

    # 重みを変える（例: 指数7:気配3）
    python paddock_predict.py --shisu shisu.csv --kehai k.csv --w-shisu 0.7 --w-kehai 0.3
    python paddock_predict.py --selftest

CSV形式:
  shisu.csv : umaban,shisu[,horse]     （指数。負値OK）
  kehai     : paddock_compare の field_gait_compare.csv（umaban,kehai_score を含む）
"""
import argparse, csv, os


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def norm100(d):
    """{umaban: value} を field 内で 0〜100 に正規化（高いほど良い）。"""
    vals = [v for v in d.values() if v is not None]
    if not vals:
        return {k: None for k in d}
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return {k: (50.0 if v is not None else None) for k, v in d.items()}
    return {k: (100 * (v - lo) / (hi - lo) if v is not None else None)
            for k, v in d.items()}


def combine(shisu_rows, kehai_rows, w_shisu, w_kehai):
    shisu = {}
    names = {}
    for r in shisu_rows or []:
        u = _num(r.get("umaban"))
        if u is None:
            continue
        shisu[int(u)] = _num(r.get("shisu"))
        if r.get("horse"):
            names[int(u)] = r["horse"]
    kehai = {}
    for r in kehai_rows or []:
        u = _num(r.get("umaban"))
        if u is None:
            continue
        kehai[int(u)] = _num(r.get("kehai_score"))

    umabans = sorted(set(shisu) | set(kehai))
    sN = norm100({u: shisu.get(u) for u in umabans})
    kN = norm100({u: kehai.get(u) for u in umabans})

    out = []
    for u in umabans:
        parts, wsum = 0.0, 0.0
        if sN.get(u) is not None:
            parts += w_shisu * sN[u]; wsum += w_shisu
        if kN.get(u) is not None:
            parts += w_kehai * kN[u]; wsum += w_kehai
        total = (parts / wsum) if wsum else None
        out.append({"umaban": u, "horse": names.get(u, ""),
                    "shisu": shisu.get(u), "shisu_n": sN.get(u),
                    "kehai": kehai.get(u), "kehai_n": kN.get(u),
                    "total": total})
    out.sort(key=lambda r: (r["total"] is not None, r["total"] or 0), reverse=True)
    return out


def print_table(rows, w_shisu, w_kehai):
    print(f"\n=== 総合予想（指数{w_shisu:.0%} × 気配{w_kehai:.0%}） ===")
    print(f"{'順':>2} {'馬番':>3} {'馬名':<12} {'総合':>6} | {'指数':>6}→{'':>5} {'気配':>6}→{'':>5}")
    print("-" * 60)
    for i, r in enumerate(rows, 1):
        tot = "  -  " if r["total"] is None else f"{r['total']:5.1f}"
        sh = "  -  " if r["shisu"] is None else f"{r['shisu']:5.0f}"
        shn = " -  " if r["shisu_n"] is None else f"{r['shisu_n']:4.0f}"
        ke = "  -  " if r["kehai"] is None else f"{r['kehai']:5.1f}"
        ken = " -  " if r["kehai_n"] is None else f"{r['kehai_n']:4.0f}"
        star = " ◎" if i == 1 else (" ○" if i == 2 else (" ▲" if i == 3 else ""))
        print(f"{i:>2} {r['umaban']:>3} {r['horse']:<12} {tot:>6} | "
              f"{sh:>6}→{shn:>4} {ke:>6}→{ken:>4}{star}")
    print("\n◎○▲=総合上位 / 「→」は field内0〜100の正規化値。")
    print("※ 相対比較・参考です。指数=能力の下地、気配=当日の動き。勝敗の断定ではありません。")


def selftest():
    shisu = [{"umaban": "1", "shisu": "-5", "horse": "A"},
             {"umaban": "2", "shisu": "-16", "horse": "B"},
             {"umaban": "3", "shisu": "3", "horse": "C"}]
    kehai = [{"umaban": "1", "kehai_score": "40"},
             {"umaban": "2", "kehai_score": "80"},
             {"umaban": "3", "kehai_score": "50"}]
    rows = combine(shisu, kehai, 0.6, 0.4)
    # 指数トップは3番、気配トップは2番。指数60%重視なら総合1位は3番のはず
    assert rows[0]["umaban"] == 3, [r["umaban"] for r in rows]
    print_table(rows, 0.6, 0.4)
    print("SELFTEST PASSED (指数×気配の合成ランキングが動作)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shisu", help="指数CSV（umaban,shisu[,horse]）")
    ap.add_argument("--kehai", help="気配CSV（paddock_compare の field_gait_compare.csv）")
    ap.add_argument("--w-shisu", dest="w_shisu", type=float, default=0.6)
    ap.add_argument("--w-kehai", dest="w_kehai", type=float, default=0.4)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest(); return
    if not args.shisu and not args.kehai:
        ap.error("--shisu か --kehai を指定してください")
    sr = read_csv(args.shisu) if args.shisu and os.path.exists(args.shisu) else None
    kr = read_csv(args.kehai) if args.kehai and os.path.exists(args.kehai) else None
    ws, wk = args.w_shisu, (args.w_kehai if kr else 0.0)
    if not kr:
        ws, wk = 1.0, 0.0
    rows = combine(sr, kr, ws, wk)
    print_table(rows, ws, wk)


if __name__ == "__main__":
    main()
