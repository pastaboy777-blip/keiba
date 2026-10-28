#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""近5走ラップのグラフ化＋持続力(後半の落ち込み)抽出  lap_graph.py

出走馬ごとに、近5走の「ラップ（区間タイム）」を1頭1枚の折れ線にして、
『後半のラップが落ち込まない（＝ペースが垂れない／持続力のある）馬』を
スコア化して並べる、自己完結HTML(ダークテーマ・SVG)を生成する。

― 読み方 ―
  ・各馬カードの折れ線：横=ラップ番号(序盤→終盤)、縦=速さ(上ほど速い=秒が小)。
    線が右側で「落ち込む(下がる)」＝後半で失速している。
  ・濃い線＝新しい走、薄い線＝古い走（recency sequential）。
  ・上部ランキング：後半の落ち込み(late_drop)が小さい順＝垂れない馬順。

late_drop = (後半ラップ平均 − 前半ラップ平均)[秒]。
  +が大きい＝後半で遅くなる(垂れ)。0前後/マイナス＝持続 or 尻上がり。
近5走を新しい走ほど重く加重平均し、持続スコア(0-100)と判定(◎○△×)を付ける。

― データ入力（貼り付け）形式 ―
  馬ごとにブロック。1行目=馬名(先頭に馬番や#可)。続く最大5行がラップ行。
  ラップ行 = 任意ラベル + 区間タイムの並び（区切りは空白/ - / , / ・ / 、）。
  数字が3つ以上並んだ行をラップ行とみなす。空行で次の馬。
  例:
    6 エコロスヴァル
    10/22 大井1200: 12.3 11.0 11.4 12.0 12.6 13.0
    10/8  船橋1200: 12.5 11.2 11.6 12.1 12.8 13.3
  （新しい走を上から並べる想定。--oldest-first で旧→新として扱う）

使い方:
  python3 lap_graph.py data.txt -o laps.html
  cat data.txt | python3 lap_graph.py -o laps.html --title 大井10R
  python3 lap_graph.py --selftest
"""
import argparse
import html
import math
import re
import sys

# ―― recency sequential（単一色相=青、薄→濃 = 古→新）――
RAMP = ["#bcd3f2", "#8fb8ea", "#5e97e0", "#2a78d6", "#17529e"]

WEIGHTS_RECENCY = [1.0, 0.85, 0.7, 0.55, 0.4]  # 新→旧の加重


# ───────────────────────── パース ─────────────────────────
NUM = re.compile(r"\d+\.?\d*")


def _laps_in(line):
    """行から区間タイムの並びを取り出す。3つ以上の数値が並べばラップ行。"""
    # ラベル(コロンや全角コロンの後ろを本体とみなす。無ければ行全体)
    body = line
    for sep in (":", "："):
        if sep in body:
            body = body.split(sep, 1)[1]
            break
    nums = [float(x) for x in NUM.findall(body)]
    # 区間タイムらしい値(5〜20秒)だけ採用。馬番や日付の数字を除外
    laps = [v for v in nums if 5.0 <= v <= 20.0]
    return laps if len(laps) >= 3 else None


def _label_of(line):
    """ラップ行のラベル(日付・開催など)。コロン前、無ければ先頭の数値列前。"""
    for sep in (":", "："):
        if sep in line:
            return line.split(sep, 1)[0].strip()
    m = NUM.search(line)
    # 先頭に日付っぽいものがあればそこまで
    head = line[:m.start()].strip() if m else line.strip()
    return head or "走"


def parse_blocks(text, oldest_first=False):
    """テキスト→[{'name':..,'races':[{'label':..,'laps':[..]}, ...]}]。"""
    horses = []
    cur = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            cur = None
            continue
        laps = _laps_in(line)
        if laps is None:
            # 馬ヘッダ（名前）。先頭の # や 馬番 を除去
            name = line.strip().lstrip("#").strip()
            name = re.sub(r"^\d+[\s\.．、]+", "", name)  # 先頭の馬番
            cur = {"name": name or f"馬{len(horses)+1}", "races": []}
            horses.append(cur)
        else:
            if cur is None:  # 名前行が無いままラップ→無名馬
                cur = {"name": f"馬{len(horses)+1}", "races": []}
                horses.append(cur)
            if len(cur["races"]) < 5:
                cur["races"].append({"label": _label_of(line), "laps": laps})
    # 近5走・新→旧に正規化
    for h in horses:
        if oldest_first:
            h["races"] = list(reversed(h["races"]))
        h["races"] = h["races"][:5]
    return [h for h in horses if h["races"]]


# ───────────────────────── 指標 ─────────────────────────
def race_metrics(laps):
    n = len(laps)
    half = n // 2
    front = sum(laps[:half]) / half if half else laps[0]
    back = sum(laps[n - half:]) / half if half else laps[-1]
    late_drop = back - front                       # +=後半で遅く(垂れ)
    last_drop = laps[-1] - min(laps)               # ラスト1本の垂れ
    return {"front": front, "back": back, "late_drop": late_drop,
            "last_drop": last_drop, "n": n}


def horse_metrics(races):
    """新→旧順の races から持続スコアを算出。"""
    drops, w = [], []
    for i, r in enumerate(races):
        m = race_metrics(r["laps"])
        r["m"] = m
        drops.append(m["late_drop"])
        w.append(WEIGHTS_RECENCY[i] if i < len(WEIGHTS_RECENCY) else 0.3)
    wmean = sum(d * wi for d, wi in zip(drops, w)) / sum(w)
    # 安定度（走ごとのばらつき小＝安定して垂れない）
    var = sum((d - (sum(drops) / len(drops))) ** 2 for d in drops) / len(drops)
    std = math.sqrt(var)
    # 持続スコア: late_drop が小さいほど高い。+1.2秒で0点,-0.3秒で100点目安
    score = max(0.0, min(100.0, 100.0 * (1.2 - wmean) / 1.5))
    verdict = ("◎ 後半垂れない(持続)" if score >= 72 else
               "○ ほぼ維持"       if score >= 55 else
               "△ やや垂れる"     if score >= 40 else
               "× 後半失速")
    return {"late_drop_w": wmean, "std": std, "score": round(score, 1),
            "verdict": verdict}


# ───────────────────────── 描画(SVG) ─────────────────────────
def _svg_lap_chart(races, w=460, h=200, pad=34):
    """1頭ぶんのラップ折れ線SVG。縦=速さ(上ほど速い=秒小)。"""
    alllaps = [v for r in races for v in r["laps"]]
    lo, hi = min(alllaps), max(alllaps)
    if hi - lo < 1e-6:
        hi = lo + 1.0
    maxn = max(len(r["laps"]) for r in races)
    pad_l, pad_b, pad_t, pad_r = pad + 10, pad, 14, 54

    def X(i):
        return pad_l + (w - pad_l - pad_r) * (i / max(1, maxn - 1))

    def Y(sec):   # 秒が小さい(速い)ほど上
        return pad_t + (h - pad_t - pad_b) * ((sec - lo) / (hi - lo))

    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" preserveAspectRatio="xMidYMid meet" '
           f'role="img" font-family="system-ui,sans-serif">']
    # 速さ目盛(秒)。上=速い
    for frac in (0.0, 0.5, 1.0):
        sec = lo + (hi - lo) * frac
        y = Y(sec)
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" '
                   f'stroke="#33332f" stroke-width="1"/>')
        out.append(f'<text x="{pad_l-6}" y="{y+3:.1f}" text-anchor="end" '
                   f'font-size="9" fill="#9a998f">{sec:.1f}s</text>')
    out.append(f'<text x="{pad_l-28}" y="{pad_t+8}" font-size="8.5" fill="#9a998f" '
               f'transform="rotate(-90 {pad_l-28} {pad_t+8})">速い↑</text>')
    # 各走の折れ線（古→薄, 新→濃）
    ncol = len(races)
    for idx in range(ncol - 1, -1, -1):          # 古い走を先に(下地)
        r = races[idx]
        # races は新→旧順。recencyランク: idx=0が最新
        shade = RAMP[-1 - min(idx, len(RAMP) - 1)]
        pts = []
        for i, sec in enumerate(r["laps"]):
            pts.append(f"{X(i):.1f},{Y(sec):.1f}")
        emph = 2.6 if idx == 0 else 1.6
        out.append(f'<polyline points="{" ".join(pts)}" fill="none" '
                   f'stroke="{shade}" stroke-width="{emph}" '
                   f'stroke-linejoin="round" stroke-linecap="round"/>')
        for i, sec in enumerate(r["laps"]):
            r_ = 3.2 if idx == 0 else 2.2
            out.append(f'<circle cx="{X(i):.1f}" cy="{Y(sec):.1f}" r="{r_}" '
                       f'fill="{shade}"><title>{html.escape(r["label"])}  '
                       f'{i+1}本目 {sec:.1f}s</title></circle>')
        # 直近2走は末尾にラベル
        if idx <= 1:
            lx, ly = X(len(r["laps"]) - 1) + 4, Y(r["laps"][-1]) + 3
            out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="8.5" '
                       f'fill="{shade}">{html.escape(r["label"][:7])}</text>')
    # x軸ラベル
    out.append(f'<text x="{pad_l}" y="{h-6}" font-size="9" fill="#9a998f">序盤</text>')
    out.append(f'<text x="{w-pad_r}" y="{h-6}" font-size="9" fill="#9a998f" '
               f'text-anchor="end">終盤→</text>')
    out.append("</svg>")
    return "".join(out)


def render(horses, title="レース"):
    # ランキング（late_drop_w 昇順＝垂れない順）
    ranked = sorted(horses, key=lambda h: h["mh"]["late_drop_w"])
    rows = []
    for rank, h in enumerate(ranked, 1):
        mh = h["mh"]
        badge = ("#1baf7a" if mh["score"] >= 72 else "#eda100"
                 if mh["score"] >= 55 else "#eb6834" if mh["score"] >= 40 else "#e34948")
        rows.append(
            f'<tr><td class="rk">{rank}</td><td>{html.escape(h["name"])}</td>'
            f'<td><b style="color:{badge}">{mh["score"]:.0f}</b></td>'
            f'<td>{mh["late_drop_w"]:+.2f}s</td><td>±{mh["std"]:.2f}</td>'
            f'<td style="color:{badge}">{html.escape(mh["verdict"])}</td></tr>')
    rank_table = (
        '<table class="rank"><thead><tr><th>#</th><th>馬名</th>'
        '<th>持続<br>スコア</th><th>後半の<br>落ち込み</th><th>ばらつき</th>'
        '<th>判定</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>")

    cards = []
    for h in ranked:
        mh = h["mh"]
        chart = _svg_lap_chart(h["races"])
        racelist = "・".join(html.escape(r["label"][:9]) for r in h["races"])
        cards.append(
            f'<div class="card"><div class="ch"><span class="nm">'
            f'{html.escape(h["name"])}</span>'
            f'<span class="sc" style="color:{"#1baf7a" if mh["score"]>=72 else "#eda100" if mh["score"]>=55 else "#eb6834" if mh["score"]>=40 else "#e34948"}">'
            f'持続 {mh["score"]:.0f} / {html.escape(mh["verdict"])}</span></div>'
            f'{chart}<div class="rl">近走: {racelist}</div></div>')

    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} 近5走ラップ</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#141413;color:#f0efec;
   font-family:system-ui,-apple-system,"Hiragino Kaku Gothic ProN",sans-serif}}
 .wrap{{max-width:1100px;margin:0 auto;padding:16px}}
 h1{{font-size:18px;margin:4px 0 2px}} .sub{{color:#9a998f;font-size:12px;margin-bottom:14px}}
 table.rank{{width:100%;border-collapse:collapse;margin-bottom:22px;font-size:13px}}
 .rank th,.rank td{{padding:6px 8px;border-bottom:1px solid #2a2a27;text-align:left}}
 .rank th{{color:#9a998f;font-weight:600;font-size:11px}}
 .rank td.rk{{color:#9a998f;width:28px}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}}
 .card{{background:#1a1a19;border:1px solid #2a2a27;border-radius:10px;padding:10px 12px}}
 .ch{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px}}
 .nm{{font-size:14px;font-weight:700}} .sc{{font-size:12px;font-weight:700}}
 .rl{{color:#9a998f;font-size:10.5px;margin-top:2px}}
 .note{{color:#9a998f;font-size:11px;margin:10px 0 18px;line-height:1.6}}
</style></head><body><div class="wrap">
<h1>{html.escape(title)}　近5走ラップ / 後半の持続力</h1>
<div class="sub">縦=速さ(上ほど速い)・濃い線=新しい走。右で線が落ち込む＝後半失速。
持続スコアが高い＝後半のラップが垂れない馬。</div>
{rank_table}
<div class="note">late_drop＝(後半ラップ平均−前半ラップ平均)。+が大きいほど後半で遅くなる。
近5走を新しい走ほど重く加重。※レースのペース・距離・馬場で絶対値は変わるため、
馬同士の比較と各馬の近走トレンドで読むこと。</div>
<div class="grid">{"".join(cards)}</div>
</div></body></html>"""


def build(text, out, title="レース", oldest_first=False):
    horses = parse_blocks(text, oldest_first=oldest_first)
    if not horses:
        raise ValueError("ラップデータを読み取れませんでした（形式を確認）")
    for h in horses:
        h["mh"] = horse_metrics(h["races"])
    htmltxt = render(horses, title)
    with open(out, "w", encoding="utf-8") as f:
        f.write(htmltxt)
    return horses


# ───────────────────────── selftest ─────────────────────────
def selftest():
    text = """
1 サステナ号
10/22 大井1200: 12.5 11.3 11.6 11.7 11.8 11.9
10/8  船橋1200: 12.6 11.4 11.7 11.8 11.9 12.0
9/20  大井1400: 12.7 11.5 11.8 11.9 12.0 12.1 12.2

2 バテ夫号
10/20 大井1200: 12.0 10.8 11.2 12.3 13.2 14.0
10/5  川崎1200: 12.1 10.9 11.4 12.6 13.5 14.3
9/18  大井1200: 12.2 11.0 11.5 12.7 13.6 14.4
"""
    import tempfile, os
    out = os.path.join(tempfile.mkdtemp(), "laps.html")
    horses = build(text, out, title="selftest")
    by = {h["name"]: h for h in horses}
    sus = by["サステナ号"]["mh"]
    bat = by["バテ夫号"]["mh"]
    print(f"サステナ号: late_drop {sus['late_drop_w']:+.2f}s  持続{sus['score']:.0f} {sus['verdict']}")
    print(f"バテ夫号  : late_drop {bat['late_drop_w']:+.2f}s  持続{bat['score']:.0f} {bat['verdict']}")
    assert sus["late_drop_w"] < bat["late_drop_w"], "垂れない馬の方がlate_dropは小さいはず"
    assert sus["score"] > bat["score"], "持続スコアの大小が逆"
    assert sus["score"] >= 55 and bat["score"] <= 45, "スコア域が不適切"
    doc = open(out, encoding="utf-8").read()
    assert "近5走ラップ" in doc and "<svg" in doc and "持続" in doc
    print(f"HTML: {out}")
    print("SELFTEST PASSED (垂れない馬>失速馬を判別・グラフHTML生成)")


def main():
    ap = argparse.ArgumentParser(description="近5走ラップのグラフ化＋後半持続力の抽出")
    ap.add_argument("data", nargs="?", help="ラップデータのテキスト(省略時は標準入力)")
    ap.add_argument("-o", "--out", default="laps.html")
    ap.add_argument("--title", default="レース")
    ap.add_argument("--oldest-first", action="store_true",
                    help="各馬のラップ行が旧→新で並んでいる場合")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if args.data:
        text = open(args.data, encoding="utf-8").read()
    else:
        text = sys.stdin.read()
    horses = build(text, args.out, title=args.title, oldest_first=args.oldest_first)
    ranked = sorted(horses, key=lambda h: h["mh"]["late_drop_w"])
    print(f"保存: {args.out}（{len(horses)}頭）")
    print("―― 後半が垂れない順（持続スコア）――")
    for i, h in enumerate(ranked, 1):
        mh = h["mh"]
        print(f"  {i:2}. {h['name']:　<12} 持続{mh['score']:5.1f}  "
              f"late_drop {mh['late_drop_w']:+.2f}s  {mh['verdict']}")


if __name__ == "__main__":
    main()
