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
import argparse, csv, statistics, sys

# (A)で逆算した紙面指数の係数プリセット: place → {距離: (距離指数k[点/秒], 基準タイム[秒])}
# 指数 = -k × (走破タイム − 基準タイム − 馬場差)。紙面値と一致（大井1200 76.1→-1 等）。
# 1800mは紙面プリセットに無いため【暫定・推定値】。1200/1400/1600の(k,base)傾向
#   （k: 200mごとに約 -1.0 / base: 200mごとに約 +14.1秒）を1600から線形外挿したもの:
#     k ≈ 8.0 - 1.0 = 7.0 、 base ≈ 104.2 + 14.1 = 118.3
#   実測の紙面係数が得られ次第、差し替えること。
PRESETS = {
    "大井": {1200: (10.0, 76.0), 1400: (9.0, 90.2), 1600: (8.0, 104.2),
             1800: (7.0, 118.3)},  # 1800は暫定外挿値（上記コメント参照）
}


def preset(place, dist):
    """place・距離から (距離指数, 基準タイム) を返す。無ければ None。"""
    return PRESETS.get(place, {}).get(int(dist))


def interp_coef(place, dist):
    """距離を跨ぐ正規化(暫定・推定): place・距離から (距離指数k, 基準タイム) を内挿で推定。
    既存PRESETSに無い距離(例1800が無い場合など)でも、近傍距離から線形内挿してk/baseを求める。
      - 既知距離ならそのプリセット値をそのまま返す（内挿不要）。
      - 既知点の範囲内なら、距離で挟む近傍2点から線形内挿する。
      - 範囲外なら最近傍点の値で代用し、警告を出す（外挿はしない＝暫定の最近傍近似）。
    戻り値: (k, base)。place が未知（プリセット無し）なら None。
    ※ あくまで既知点からの内挿・近似であり、紙面実測係数ではない点に注意。"""
    table = PRESETS.get(place)
    if not table:
        return None
    dist = int(dist)
    if dist in table:
        return table[dist]
    known = sorted(table)  # 距離の昇順
    if dist < known[0] or dist > known[-1]:
        near = known[0] if dist < known[0] else known[-1]
        print(f"[警告] {place}{dist}m はプリセット既知範囲({known[0]}〜{known[-1]}m)外。"
              f"最近傍 {near}m の値で代用(暫定)。", file=sys.stderr)
        return table[near]
    # 距離で挟む近傍2点 (lo <= dist <= hi) から線形内挿
    lo = max(d for d in known if d <= dist)
    hi = min(d for d in known if d >= dist)
    k_lo, b_lo = table[lo]
    k_hi, b_hi = table[hi]
    r = (dist - lo) / (hi - lo)
    return (k_lo + (k_hi - k_lo) * r, b_lo + (b_hi - b_lo) * r)


def to_sec(t):
    """'1:15.8' でも '75.8' でも秒(float)に。"""
    t = str(t).strip()
    if ":" in t:
        m, s = t.split(":")
        return int(m) * 60 + float(s)
    return float(t)


def speed_index(time_sec, base_time, dist_coef, track_diff=0.0):
    """紙面互換のスピード指数。指数 = -k×(走破タイム − 基準タイム − 馬場差)。
    馬場差(track_diff): 負=速い日(基準より速い時計が出る日)。走破タイムが基準・馬場を
    考慮して速いほど指数が高い。"""
    return -dist_coef * (time_sec - base_time - track_diff)


def estimate_track_diff(win_times_by_dist, preset):
    """馬場差(track bias)補正の枠組み(暫定・推定)。
    同開催日・同距離の複数レースの勝ち時計から、その日の馬場の速さ(基準との差,秒)を推定する。
    win_times_by_dist: {距離m: 勝ち時計}  値は 秒/'1:16.1' の単一、または複数のリストを許容。
    preset: {距離m: (k, base)} （PRESETS[place] を渡す想定。各距離の base を参照する）。
    手法: 各レースの残差 = base − 勝ち時計 を全距離分あつめ、その中央値を『その日の馬場差』とする。
      正 = 基準より速い時計が出る日（＝速い馬場）／ 負 = 遅い馬場。
      （中央値を使うのは、特定レースの展開・大波乱の外れ値に強くするため＝頑健推定。）
    ※ speed_index() の track_diff は符号が逆（負=速い日）の約束なので、指数計算に渡すときは
       符号を反転させること: track_diff = -estimate_track_diff(...)。
    対象距離のプリセットが無い場合、その距離は無視する（base が無く残差を取れないため）。
    戻り値: 馬場差(秒, float)。有効な残差が1つも無ければ 0.0。"""
    residuals = []
    for dist, times in win_times_by_dist.items():
        coef = preset.get(int(dist))
        if not coef:
            continue  # その距離の基準タイムが無いので馬場差の推定に使えない（暫定的に無視）
        base = coef[1]
        if not isinstance(times, (list, tuple)):
            times = [times]
        for t in times:
            residuals.append(base - to_sec(t))  # 正=基準より速い＝馬場が速い
    if not residuals:
        return 0.0
    return float(statistics.median(residuals))


def class_adjust(index, horse_class, class_offsets=None):
    """クラス(格)補正(暫定・推定)。クラスごとの平均時計差を指数側のオフセットとして与え補正する。
    class_offsets: {クラス名: 補正ポイント} の dict。上位クラスほど時計が速い傾向を、
      同じ生タイムでも指数を割り引く／積み増すなどの平準化に使う想定。
    class_offsets が None、または horse_class が dict に無ければ 0（無補正）。
    戻り値: index + offset。あくまでクラス間の平均差を近似する暫定補正。"""
    off = (class_offsets or {}).get(horse_class, 0.0)
    return index + off


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
    # place＋距離のプリセットがあれば係数を自動適用（(A)で復元した紙面互換係数）
    if args.place and args.dist and preset(args.place, args.dist):
        k, base_time = preset(args.place, args.dist)
        src = f"{args.place}{int(args.dist)}m プリセット"
    else:
        if args.dist_coef is None or args.base_time is None:
            raise SystemExit("--place/--dist のプリセットが無い場合は --dist-coef と --base-time を指定してください")
        k, base_time = args.dist_coef, to_sec(args.base_time)
        src = "手動指定"
    idx = speed_index(to_sec(args.time), base_time, k, args.track_diff)
    md = f" 馬場差{args.track_diff:+.1f}s" if args.track_diff else ""
    print(f"[{src}] 距離指数k={k} 基準{base_time:.1f}s{md}")
    print(f"走破タイム {args.time}（{to_sec(args.time):.1f}s） → 指数 = {idx:.1f}")


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

    # (a) estimate_track_diff: 速い日=正の馬場差 / 遅い日=負 を返す（暫定・推定の符号確認）
    fast = estimate_track_diff({1200: [75.0, 75.2], 1400: 89.0}, PRESETS["大井"])  # 基準より速い
    slow = estimate_track_diff({1200: 77.0, 1400: 91.5}, PRESETS["大井"])          # 基準より遅い
    assert fast > 0, f"速い日の馬場差は正のはず: {fast}"
    assert slow < 0, f"遅い日の馬場差は負のはず: {slow}"
    print(f"(a) 馬場差推定: 速い日={fast:+.2f}s(>0) 遅い日={slow:+.2f}s(<0)")

    # (b) interp_coef: プリセットに無い距離を近傍から線形内挿（1700は1600と1800の中間的な値）
    k16, b16 = interp_coef("大井", 1600)
    k18, b18 = interp_coef("大井", 1800)
    k17, b17 = interp_coef("大井", 1700)
    assert k18 < k17 < k16, f"1700のkは1600と1800の中間のはず: {k16},{k17},{k18}"
    assert b16 < b17 < b18, f"1700のbaseは1600と1800の中間のはず: {b16},{b17},{b18}"
    assert k18 < k16 and b18 > b16, "1800は1600から見てk減少・base増加の傾向を継続するはず"
    print(f"(b) 内挿: 1600(k={k16},base={b16}) 1700(k={k17:.2f},base={b17:.2f}) "
          f"1800(k={k18},base={b18}) ＝中間的")

    # (c) class_adjust: クラスオフセットが単調なら出力も単調、無指定クラスは無補正
    offs = {"B2": -4.0, "B1": -2.0, "A": 0.0}
    base_idx = 50.0
    cb2 = class_adjust(base_idx, "B2", offs)
    cb1 = class_adjust(base_idx, "B1", offs)
    ca = class_adjust(base_idx, "A", offs)
    assert cb2 < cb1 < ca, f"クラス補正は単調のはず: {cb2},{cb1},{ca}"
    assert class_adjust(base_idx, "未知クラス", offs) == base_idx, "未知クラスは無補正のはず"
    assert class_adjust(base_idx, "A", None) == base_idx, "offsets無しは無補正のはず"
    print(f"(c) クラス補正(単調): B2={cb2:.1f} < B1={cb1:.1f} < A={ca:.1f}")

    print("SELFTEST PASSED (逆算＋馬場差推定＋距離内挿＋クラス補正が正しく動作)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    pc = sub.add_parser("calc", help="指数を計算する（大井はプリセット自動適用）")
    pc.add_argument("--time", required=True, help="走破タイム（1:16.1 でも 76.1 でも可）")
    pc.add_argument("--place", help="競馬場（例: 大井）プリセット適用")
    pc.add_argument("--dist", type=int, help="距離m（例: 1200）プリセット適用")
    pc.add_argument("--track-diff", type=float, default=0.0, help="馬場差(秒・負=速い日)")
    pc.add_argument("--base-time", help="基準タイム（プリセット外の手動指定用）")
    pc.add_argument("--dist-coef", type=float, help="距離指数（プリセット外の手動指定用）")
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
