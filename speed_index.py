#!/usr/bin/env python3
"""
speed_index.py — スピード指数を「作る」＆新聞の指数式を「逆算する」

スピード指数の定番の骨格（西田式系）:
    指数 =（基準タイム − 走破タイム）× 距離指数 ＋ 馬場指数 ＋ 基準値

同じ距離・同じ日なら、指数は走破タイムの一次式:
    指数 = −距離指数 × 走破タイム ＋ 定数
なので、新聞の (走破タイム, 指数) を数点あつめて直線回帰すれば、
    傾き  → 距離指数
    切片  → 基準タイム×距離指数 ＋ 馬場 ＋ 基準値
が逆算でき、新聞の指数式を「盗める」。

使い方:
    # 指数を計算する（自分の指数を作る）
    python speed_index.py calc --time 75.8 --base-time 73.0 --dist-coef 1.25
    # 新聞の (走破タイム,指数) から式を逆算する（同一距離のデータ）
    #   data.csv: time,index   の2列（同じ距離・できれば同じ馬場）
    python speed_index.py fit data.csv
    python speed_index.py --selftest

走破タイムは秒（例 1:15.8 → 75.8）。距離指数は「1秒あたりのポイント」。
"""
import argparse, csv


def to_sec(t):
    """'1:15.8' でも '75.8' でも秒(float)に。"""
    t = str(t).strip()
    if ":" in t:
        m, s = t.split(":")
        return int(m) * 60 + float(s)
    return float(t)


def speed_index(time_sec, base_time, dist_coef, track_adj=0.0, base=0.0):
    """スピード指数を計算。走破タイムが基準より速いほど高い。"""
    return (base_time - time_sec) * dist_coef + track_adj + base


def fit(samples):
    """同一距離の [(走破タイム秒, 指数)] を直線回帰し、指数式のパラメータを逆算。
    指数 = slope*time + intercept  →  距離指数 = -slope。
    戻り値: dict(dist_coef, slope, intercept, r2, n, const)。"""
    xs = [to_sec(t) for t, _ in samples]
    ys = [float(i) for _, i in samples]
    n = len(xs)
    if n < 2:
        raise ValueError("2点以上必要です")
    mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        raise ValueError("走破タイムがすべて同じで回帰できません")
    slope = sxy / sxx
    intercept = my - slope * mx
    # 決定係数 r^2
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    return {"dist_coef": -slope, "slope": slope, "intercept": intercept,
            "const": intercept, "r2": r2, "n": n}


def cmd_calc(args):
    idx = speed_index(to_sec(args.time), to_sec(args.base_time),
                      args.dist_coef, args.track_adj, args.base)
    print(f"走破タイム {args.time}（{to_sec(args.time):.1f}s） / 基準 {args.base_time} / "
          f"距離指数 {args.dist_coef} → 指数 = {idx:.1f}")


def cmd_fit(args):
    with open(args.data, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    samples = [(r["time"], r["index"]) for r in rows if r.get("time") and r.get("index")]
    res = fit(samples)
    print(f"\n=== 新聞の指数式を逆算（{res['n']}点・同一距離想定） ===")
    print(f"  距離指数（1秒あたりのポイント）: {res['dist_coef']:.3f}")
    print(f"  切片（基準タイム×距離指数＋馬場＋基準値）: {res['const']:.2f}")
    print(f"  当てはまり r² = {res['r2']:.3f}")
    print(f"\n  復元式:  指数 = ({res['const']/res['dist_coef']:.2f} − 走破タイム秒) × {res['dist_coef']:.3f}")
    print(f"           （＝基準タイム {res['const']/res['dist_coef']:.2f}s 相当を0点とする）")
    if res["r2"] < 0.9:
        print("  ※ r²が低め: 距離/馬場が混ざっているか、点が少ない/誤読の可能性。")
    print("\n距離ごとに同じ逆算を繰り返せば、距離指数の表が完成＝新聞の指数式を再現できます。")


def selftest():
    # 既知の式で指数を生成→逆算で係数を復元できるか
    base_time, k = 73.0, 1.25   # 基準73.0秒、距離指数1.25、基準値0
    samples = [(t, speed_index(t, base_time, k)) for t in (72.0, 73.0, 74.5, 76.0)]
    res = fit(samples)
    assert abs(res["dist_coef"] - k) < 1e-6, res
    recovered_base = res["const"] / res["dist_coef"]
    assert abs(recovered_base - base_time) < 1e-6, recovered_base
    print(f"復元: 距離指数={res['dist_coef']:.3f}(正解{k}) 基準タイム={recovered_base:.2f}(正解{base_time})")
    print("SELFTEST PASSED (指数式の逆算＝『盗み』が正しく動作)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    pc = sub.add_parser("calc", help="指数を計算する")
    pc.add_argument("--time", required=True); pc.add_argument("--base-time", required=True)
    pc.add_argument("--dist-coef", type=float, required=True)
    pc.add_argument("--track-adj", type=float, default=0.0)
    pc.add_argument("--base", type=float, default=0.0)
    pf = sub.add_parser("fit", help="新聞の(time,index)から式を逆算")
    pf.add_argument("data", help="CSV: time,index の2列（同一距離）")
    args = ap.parse_args()
    if args.selftest:
        selftest(); return
    if args.cmd == "calc":
        cmd_calc(args)
    elif args.cmd == "fit":
        cmd_fit(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
