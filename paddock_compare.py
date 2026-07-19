#!/usr/bin/env python3
"""
paddock_compare.py — 全頭の歩様指標を横並び比較・ランキング表示

paddock_segment.py --gait で出力される各馬の *_gait_metrics.csv を集め、
1レース分を横並びの比較表にする。指標ごとに相対順位(field内の位置)を付け、
「気配比較」をひと目で分かるようにする。

使い方:
    # カレントの *_gait_metrics.csv を全部集めて比較
    python paddock_compare.py
    # ディレクトリ/glob指定
    python paddock_compare.py "race1/*_gait_metrics.csv"
    # HTML表も出力（ブラウザで見やすい・相対ヒートマップ付き）
    python paddock_compare.py --html race1_compare.html
    python paddock_compare.py --selftest

注意: 指標の「良し悪し」は馬・状況で変わる。本ツールは相対順位を示すだけで、
      勝ち負けを断定しない。矢印は「一般に好まれる向き」の目安。
"""
import argparse, glob, os, sys

# 指標の定義: (キー, 表示名, 好ましい向き) direction: -1=小さいほど良い, +1=大きいほど良い, 0=中立
METRICS = [
    ("stride_freq_hz",      "ストライド頻度",   0),
    ("stride_regularity_s", "リズム安定(小=安定)", -1),
    ("stride_len_norm",     "ストライド長",     +1),
    ("head_bob_norm",       "頭の上下動(小=落着)", -1),
    ("topline_stability",   "背中の安定(小=安定)", -1),
]


def load_rows(patterns):
    """CSV群を読み、[{umaban, source, metric...}] を返す。"""
    import pandas as pd
    files = []
    for p in patterns:
        files += glob.glob(p)
    files = sorted(set(files))
    rows = []
    for f in files:
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if df.empty:
            continue
        r = df.iloc[0].to_dict()
        r["_file"] = f
        r["umaban"] = _guess_umaban(f, r)
        rows.append(r)
    return rows


def _guess_umaban(path, row):
    import re
    m = re.search(r"uma(\d+)", os.path.basename(path))
    if m:
        return int(m.group(1))
    src = str(row.get("source", ""))
    m = re.search(r"uma(\d+)", src)
    return int(m.group(1)) if m else None


def rank_field(rows):
    """指標ごとに field 内順位(1=好ましい向きで最上位)を付与。"""
    import pandas as pd, numpy as np
    df = pd.DataFrame(rows)
    for key, _, direction in METRICS:
        if key not in df:
            df[key] = np.nan
        vals = pd.to_numeric(df[key], errors="coerce")
        if direction == 0:
            df[key + "_rank"] = np.nan  # 中立指標は順位を付けない
        else:
            asc = (direction < 0)  # 小さいほど良い→昇順で1位
            df[key + "_rank"] = vals.rank(ascending=asc, method="min")
    return df


# 気配スコアの重み(調教理論の裏付け: 背の安定=ハミ受け/透過性, 頭の落ち着き=リラックス,
# ストライドの伸び=後肢の踏み込み, リズム=真直性/バランス)。相対比較であり勝敗の断定ではない。
KEHAI_WEIGHTS = {
    "topline_stability": 1.2,      # 背中の安定(丸い背・透過性)
    "head_bob_norm": 1.0,          # 頭頸の落ち着き(ハミ受け/リラックス)
    "stride_len_norm": 1.0,        # ストライドの伸び(後肢の踏み込み)
    "stride_regularity_s": 0.8,    # リズムの安定(真直性/バランス)
}


def add_kehai(df):
    """各馬の指標をfield内で0〜1に正規化し、好ましい向きに揃えて重み付き平均→
    気配スコア(0〜100, 高いほど良い)を付与する。相対比較。"""
    import numpy as np, pandas as pd
    n = len(df)
    score = pd.Series(0.0, index=df.index)
    wsum = pd.Series(0.0, index=df.index)
    for key, _, direction in METRICS:
        if direction == 0 or key not in KEHAI_WEIGHTS or key not in df:
            continue
        vals = pd.to_numeric(df[key], errors="coerce")
        vmin, vmax = vals.min(), vals.max()
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax == vmin:
            good = pd.Series(0.5, index=df.index)   # 差が無い/1頭なら中立
        else:
            good = (vals - vmin) / (vmax - vmin)
            if direction < 0:                        # 小さいほど良い指標は反転
                good = 1 - good
        w = KEHAI_WEIGHTS[key]
        m = good.notna()
        score[m] += good[m] * w
        wsum[m] += w
    df["kehai_score"] = (100 * score / wsum.replace(0, np.nan)).round(1)
    return df


def print_table(df):
    df = df.sort_values("kehai_score", ascending=False) if "kehai_score" in df else df
    print("\n=== 全頭 歩様指標 横並び比較（気配スコア順） ===")
    header = f"{'馬番':>4} | {'気配':>6} | " + " | ".join(f"{name:>14}" for _, name, _ in METRICS)
    print(header)
    print("-" * len(header))
    for _, r in df.iterrows():
        uma = r.get("umaban")
        cells = []
        for key, _, direction in METRICS:
            v = r.get(key)
            rk = r.get(key + "_rank")
            vs = "  -  " if v is None or (isinstance(v, float) and v != v) else f"{float(v):.3f}"
            mark = ""
            if direction != 0 and rk == rk and rk == 1:
                mark = "★"  # field内トップ(好ましい向き)
            cells.append(f"{vs:>13}{mark:1}")
        umas = f"{int(uma):>4}" if uma == uma and uma is not None else "  ？"
        ks = r.get("kehai_score")
        kss = "  -  " if ks is None or (isinstance(ks, float) and ks != ks) else f"{float(ks):5.1f}"
        print(f"{umas} | {kss:>6} | " + " | ".join(cells))
    print("\n気配 = 各指標を良し悪しの向きで合成した相対スコア(0〜100・高いほど良い)")
    print("★ = その指標でfield内トップ（矢印の向きで好ましい側）")
    print("※ 相対比較です。勝敗の断定ではありません。骨格付き動画での目視確認と併用してください。")


def write_html(df, path):
    import pandas as pd, numpy as np
    df = df.sort_values("kehai_score", ascending=False) if "kehai_score" in df else df
    def cell(v, rk, direction, n):
        if v is None or (isinstance(v, float) and v != v):
            return '<td style="text-align:center;color:#999">-</td>'
        bg = "#ffffff"
        if direction != 0 and rk == rk and n > 1:
            t = 1 - (rk - 1) / (n - 1)      # 1=好ましい向きの上位
            g = int(200 + 55 * t); rr = int(255 - 90 * t); bb = int(255 - 90 * t)
            bg = f"rgb({rr},{g},{bb})"
        star = "★" if (direction != 0 and rk == 1) else ""
        return f'<td style="text-align:right;background:{bg};padding:6px 10px">{float(v):.3f} {star}</td>'
    def kcell(ks):
        if ks is None or (isinstance(ks, float) and ks != ks):
            return '<td style="text-align:center;color:#999">-</td>'
        t = max(0.0, min(1.0, float(ks) / 100))
        g = int(180 + 75 * t); rr = int(255 - 120 * t); bb = int(255 - 150 * t)
        return (f'<td style="text-align:center;font-weight:700;font-size:1.1em;'
                f'background:rgb({rr},{g},{bb});padding:6px 12px">{float(ks):.1f}</td>')
    n = len(df)
    th = "".join(f"<th style='padding:6px 10px'>{name}</th>" for _, name, _ in METRICS)
    trs = []
    for _, r in df.iterrows():
        uma = r.get("umaban")
        umas = f"{int(uma)}" if uma == uma and uma is not None else "？"
        tds = "".join(cell(r.get(k), r.get(k + "_rank"), d, n) for k, _, d in METRICS)
        trs.append(f"<tr><td style='text-align:center;font-weight:700;padding:6px 10px'>{umas}</td>"
                   f"{kcell(r.get('kehai_score'))}{tds}</tr>")
    html = f"""<!doctype html><meta charset="utf-8">
<title>全頭 歩様比較（気配スコア）</title>
<style>body{{font-family:sans-serif;margin:24px}}table{{border-collapse:collapse}}
th,td{{border:1px solid #ddd}}th{{background:#333;color:#fff}}</style>
<h2>全頭 歩様指標 横並び比較（気配スコア順）</h2>
<table><thead><tr><th style='padding:6px 10px'>馬番</th>
<th style='padding:6px 10px'>気配<br>スコア</th>{th}</tr></thead>
<tbody>{''.join(trs)}</tbody></table>
<p>気配スコア(0〜100・高いほど良い)＝背の安定・頭の落ち着き・ストライドの伸び・リズムを
良し悪しの向きで合成した相対指標。濃い緑＝その指標で相対的に好ましい側 / ★＝field内トップ。
<b>相対比較であり勝敗の断定ではありません。</b>骨格付き動画での目視確認と併用してください。</p>"""
    with open(path, "w") as f:
        f.write(html)
    print(f"HTML表を保存: {path}")


def selftest():
    import pandas as pd
    rows = [
        {"umaban": 3, "stride_freq_hz": 0.80, "stride_regularity_s": 0.05,
         "stride_len_norm": 0.50, "head_bob_norm": 0.03, "topline_stability": 0.02},
        {"umaban": 7, "stride_freq_hz": 0.90, "stride_regularity_s": 0.20,
         "stride_len_norm": 0.40, "head_bob_norm": 0.10, "topline_stability": 0.08},
        {"umaban": 12, "stride_freq_hz": 0.85, "stride_regularity_s": 0.12,
         "stride_len_norm": 0.45, "head_bob_norm": 0.06, "topline_stability": 0.05},
    ]
    df = add_kehai(rank_field(rows))
    # 3番はregularity/head_bob/toplineが最小=好ましい向きで1位のはず
    idx = df.set_index("umaban")
    assert idx.loc[3, "stride_regularity_s_rank"] == 1
    assert idx.loc[3, "topline_stability_rank"] == 1
    # 3番は全指標で好ましい向き→気配スコア最上位のはず
    assert idx["kehai_score"].idxmax() == 3, idx["kehai_score"]
    print_table(df)
    print("SELFTEST PASSED (相対順位付け＋気配スコアが正しく動作)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patterns", nargs="*", default=None,
                    help="CSVのglob（既定: ./*_gait_metrics.csv）")
    ap.add_argument("--html", help="HTML比較表の出力先")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest(); return
    patterns = args.patterns or ["*_gait_metrics.csv"]
    rows = load_rows(patterns)
    if not rows:
        ap.error(f"歩様指標CSVが見つかりません: {patterns}")
    df = add_kehai(rank_field(rows))
    print_table(df)
    if args.html:
        write_html(df, args.html)
    import pandas as pd
    out = "field_gait_compare.csv"
    df.drop(columns=[c for c in df.columns if c.startswith("_")], errors="ignore").to_csv(out, index=False)
    print(f"比較CSVを保存: {out}")


if __name__ == "__main__":
    main()
