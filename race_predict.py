#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""レースの総合予想（後半持続＋スピード指数）  race_predict.py

あるレースの「出走馬＋各馬の近5走」から、
  ・後半持続（前後半ラップ差 late_drop が小さい＝垂れない）
  ・スピード指数（簡易：sec/400m が小さい＝速い）
の2本を出し、フィールド内で正規化して総合スコアにまとめ、
総合ランキング表を自己完結HTML(ダークテーマ)で描く再利用モジュール。

― 読み方 ―
  ・総合＝スピード60%＋持続40%。フィールド内の相対値(0〜100)。
  ・スピード指数：各走の「自身タイム ÷ 距離 ×400」(＝400mあたり秒)を
    近走ほど重く加重平均。小さいほど速い→高スコア。
    ※馬場差・クラス・展開は未補正の簡易指数。
  ・後半持続：各走の (後半3F − 前半3F) ＝ late_drop を加重平均。
    小さい(ゼロ/マイナス)ほど後半垂れない→高スコア。

― データ ―
  ・出走馬リスト JSON: [[馬番, 馬名, 馬ID], ...]
  ・各馬の完全データHTML: <htmldir>/<馬ID>.html（競馬ブック kanzen 保存版）
  parse_kanzen() が各馬HTMLの競走成績行から近走を取り出す。

近走加重: [1.0, .85, .7, .55, .4]（新→旧）。

使い方:
  python3 race_predict.py --field field.json --htmldir kb -o race.html --title 大井11R
  python3 race_predict.py --selftest
"""
import argparse
import html
import json
import os
import re
import sys

WEIGHTS_RECENCY = [1.0, 0.85, 0.7, 0.55, 0.4]  # 新→旧の加重

# ―― 棒グラフ色（高いほど良い＝暖色寄り、低いほど冷色）――
BAR_SPEED = "#3f8ae0"   # スピード指数バー（青）
BAR_SUST = "#1baf7a"    # 後半持続バー（緑）


# ───────────────────────── 時計 ─────────────────────────
def to_sec(t):
    """競馬ブックの走破タイムを秒(float)に。
    'M.SS.t'(例 1.41.4=101.4) / 'M:SS.t' / 'SS.t' のいずれも可。"""
    t = str(t).strip()
    if ":" in t:  # 1:41.4
        m, s = t.split(":", 1)
        return int(m) * 60 + float(s)
    parts = t.split(".")
    if len(parts) == 3:  # 1.41.4 → 1分41.4秒
        return int(parts[0]) * 60 + float(parts[1] + "." + parts[2])
    return float(t)


# ───────────────────────── パース ─────────────────────────
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")
_DATE = re.compile(r"(\d{4})年(\d+)月(\d+)日")
_DIST = re.compile(r"(\d{3,4})m")
_PACE = re.compile(r"前([\d.]+)-後([\d.]+)")
_TIME = re.compile(r"(\d+\.\d+\.\d+)")
_CHAKU = re.compile(r"(\d+)着")


def _plain_text(html_text):
    """HTMLからタグを除いた素のテキストにする。"""
    txt = _TAG.sub(" ", html_text)
    txt = html.unescape(txt)
    return _WS.sub(" ", txt)


def parse_kanzen(html_text):
    """競馬ブック kanzen の競走成績から近走を抽出して返す。

    日付をアンカーに1走ぶんずつ区切り、距離・前後半・自身タイム・着順が
    そろった「完走した1走」だけを拾う（追い切り・未出走の当該レースは除外）。
    自身タイムは距離表記の後の最初の `\\d+.\\d+.\\d+`。
    戻り値: 日付降順の list[dict]。各dict:
      {y,m,d,date(=(y,m,d)), dist(int), front, back, late_drop,
       time(str), sec(float), chaku(int)}
    """
    txt = _plain_text(html_text)
    ms = list(_DATE.finditer(txt))
    races = []
    for k, dm in enumerate(ms):
        s = dm.start()
        e = ms[k + 1].start() if k + 1 < len(ms) else len(txt)
        seg = txt[s:e]
        dist = _DIST.search(seg)
        pace = _PACE.search(seg)
        chaku = _CHAKU.search(seg)
        if not (dist and pace and chaku):
            continue
        tm = _TIME.search(seg[dist.end():])  # 距離の後の最初の時計
        if not tm:
            continue
        y, mo, da = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
        front, back = float(pace.group(1)), float(pace.group(2))
        races.append({
            "y": y, "m": mo, "d": da, "date": (y, mo, da),
            "dist": int(dist.group(1)),
            "front": front, "back": back, "late_drop": back - front,
            "time": tm.group(1), "sec": to_sec(tm.group(1)),
            "chaku": int(chaku.group(1)),
        })
    races.sort(key=lambda r: r["date"], reverse=True)  # 新しい順
    return races


# ───────────────────────── 指標 ─────────────────────────
def horse_metrics(races):
    """近5走を新しい走ほど加重し、後半持続とスピードを算出。
      drop  = late_drop=(後−前) の加重平均（小=垂れない）
      pace  = sec/400m = time/dist*400 の加重平均（小=速い）
    戻り値: {'drop','pace','n'} / 近走ゼロなら None。"""
    use = races[:5]
    if not use:
        return None
    w = [WEIGHTS_RECENCY[i] if i < len(WEIGHTS_RECENCY) else 0.3
         for i in range(len(use))]
    wsum = sum(w)
    drop = sum(r["late_drop"] * wi for r, wi in zip(use, w)) / wsum
    pace = sum((r["sec"] / r["dist"] * 400.0) * wi
               for r, wi in zip(use, w)) / wsum
    return {"drop": drop, "pace": pace, "n": len(use)}


def _norm_small_is_high(vals):
    """{key: value} を field 内 0〜100 に。値が小さいほど高スコア。"""
    xs = [v for v in vals.values() if v is not None]
    if not xs:
        return {k: None for k in vals}
    lo, hi = min(xs), max(xs)
    if hi == lo:
        return {k: (50.0 if v is not None else None) for k, v in vals.items()}
    return {k: (100.0 * (hi - v) / (hi - lo) if v is not None else None)
            for k, v in vals.items()}


# ───────────────────────── 予想 ─────────────────────────
def predict(field, html_by_id):
    """field=[[馬番,馬名,馬ID],...]、html_by_id={馬ID: html文字列}。
    全馬の持続・速度を集め、フィールド内で正規化（drop小=高/pace小=高）し、
    総合=speed*0.6+sustain*0.4。総合降順の list[dict] を返す。"""
    horses = []
    for num, name, hid in field:
        races = parse_kanzen(html_by_id.get(str(hid), "")) if hid is not None else []
        m = horse_metrics(races)
        horses.append({"umaban": num, "name": name, "horse_id": hid,
                       "races": races[:5], "m": m})
    drop = {h["umaban"]: (h["m"]["drop"] if h["m"] else None) for h in horses}
    pace = {h["umaban"]: (h["m"]["pace"] if h["m"] else None) for h in horses}
    sustain_n = _norm_small_is_high(drop)
    speed_n = _norm_small_is_high(pace)
    for h in horses:
        u = h["umaban"]
        sp, su = speed_n.get(u), sustain_n.get(u)
        h["speed_n"] = sp
        h["sustain_n"] = su
        h["drop"] = drop[u]
        h["pace"] = pace[u]
        if sp is None and su is None:
            h["total"] = None
        elif sp is None:
            h["total"] = su
        elif su is None:
            h["total"] = sp
        else:
            h["total"] = sp * 0.6 + su * 0.4
    horses.sort(key=lambda h: (h["total"] is not None, h["total"] or 0.0),
                reverse=True)
    return horses


# ───────────────────────── 描画 ─────────────────────────
def _bar(pct, color, w=120):
    """0〜100の横棒。Noneは空欄。"""
    if pct is None:
        return '<span style="color:#6a6a63">—</span>'
    fill = max(0.0, min(100.0, pct))
    return (f'<span class="bar" style="width:{w}px">'
            f'<i style="width:{fill:.1f}%;background:{color}"></i>'
            f'<b>{pct:.0f}</b></span>')


def render(rows, title="レース"):
    """総合ランキング表の自己完結HTML(ダークテーマ)を返す。"""
    trs = []
    for rank, h in enumerate(rows, 1):
        tot = ("—" if h["total"] is None
               else f'{h["total"]:.1f}')
        star = ("◎" if rank == 1 else "○" if rank == 2
                else "▲" if rank == 3 else "")
        drop_s = ("—" if h["drop"] is None else f'{h["drop"]:+.2f}s')
        nn = h["m"]["n"] if h["m"] else 0
        trs.append(
            f'<tr><td class="rk">{rank}<span class="st">{star}</span></td>'
            f'<td class="tot"><b>{tot}</b></td>'
            f'<td class="um">{html.escape(str(h["umaban"]))}</td>'
            f'<td class="nm">{html.escape(str(h["name"]))}'
            f'<span class="sub">近{nn}走</span></td>'
            f'<td>{_bar(h["speed_n"], BAR_SPEED)}</td>'
            f'<td>{_bar(h["sustain_n"], BAR_SUST)}</td>'
            f'<td class="dp">{drop_s}</td></tr>')
    table = ('<table><thead><tr><th>#</th><th>総合</th><th>馬番</th>'
             '<th>馬名</th><th>スピード指数</th><th>後半持続</th>'
             '<th>後−前</th></tr></thead><tbody>'
             + "".join(trs) + '</tbody></table>')

    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} 総合予想</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#141413;color:#f0efec;
   font-family:system-ui,-apple-system,"Hiragino Kaku Gothic ProN",sans-serif}}
 .wrap{{max-width:860px;margin:0 auto;padding:16px}}
 h1{{font-size:18px;margin:4px 0 2px}}
 .sub0{{color:#9a998f;font-size:12px;margin-bottom:14px;line-height:1.6}}
 table{{width:100%;border-collapse:collapse;font-size:13px}}
 th,td{{padding:7px 8px;border-bottom:1px solid #2a2a27;text-align:left;
   vertical-align:middle}}
 th{{color:#9a998f;font-weight:600;font-size:11px;white-space:nowrap}}
 td.rk{{color:#9a998f;width:34px;white-space:nowrap}}
 td.rk .st{{color:#eda100;margin-left:2px}}
 td.tot b{{font-size:15px}}
 td.um{{color:#9a998f;width:30px}}
 td.nm{{font-weight:700}}
 td.nm .sub{{color:#6a6a63;font-weight:400;font-size:10px;margin-left:6px}}
 td.dp{{color:#c9c7bd;font-variant-numeric:tabular-nums}}
 .bar{{position:relative;display:inline-block;height:14px;border-radius:3px;
   background:#26261f;vertical-align:middle}}
 .bar i{{position:absolute;left:0;top:0;height:100%;border-radius:3px;
   display:block}}
 .bar b{{position:absolute;right:4px;top:-1px;font-size:10px;
   color:#f0efec;line-height:16px;font-weight:600;
   text-shadow:0 0 3px #000}}
 .note{{color:#9a998f;font-size:11px;margin:16px 0 0;line-height:1.75}}
 .note b{{color:#c9c7bd}}
</style></head><body><div class="wrap">
<h1>{html.escape(title)}　総合予想（スピード指数 × 後半持続）</h1>
<div class="sub0">総合＝スピード指数60% ＋ 後半持続40%（フィールド内の相対 0〜100）。
スピード＝近走の「自身タイム÷距離×400(＝400mあたり秒)」を新しい走ほど重く加重、速いほど高い。
持続＝近走の(後半3F−前半3F)＝late_dropを加重、垂れないほど高い。</div>
{table}
<div class="note">
<b>スピード指数は簡易</b>です（sec/400m・<b>馬場差／クラスは未補正</b>）。開催日や格で時計の価値は変わります。<br>
<b>後半持続</b>は前後半ラップ差で見ており、<b>脚質・ペース依存</b>（スローで溜めた馬は小さく、ハイペースで追走した馬は大きく出やすい）。<br>
馬の<b>気配・腹圧</b>は動画が要るためここでは<b>未算出</b>です。<br>
あくまで<b>一材料</b>。実戦は<b>血統・展開（枠順・ペース・隊列）が支配</b>します。勝敗の断定ではありません。
</div>
</div></body></html>"""


# ───────────────────────── 実行 ─────────────────────────
def load_html_by_id(field, htmldir):
    """field の馬IDごとに <htmldir>/<馬ID>.html を読む。無い馬は空文字。"""
    out = {}
    for _num, _name, hid in field:
        if hid is None:
            continue
        path = os.path.join(htmldir, f"{hid}.html")
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                out[str(hid)] = f.read()
        else:
            out[str(hid)] = ""
    return out


def build(field, htmldir, out, title="レース"):
    html_by_id = load_html_by_id(field, htmldir)
    rows = predict(field, html_by_id)
    doc = render(rows, title)
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    return rows


# ───────────────────────── selftest ─────────────────────────
def _synthetic_html(front, back, times_dists, start_year=2025):
    """合成の競走成績HTML断片を作る（parse_kanzen が読める最小形）。
    times_dists: [(time_str, dist), ...] 新→旧の順。"""
    rows = []
    mo = len(times_dists)
    for i, (t, dist) in enumerate(times_dists):
        rows.append(
            f'<tr><td>{start_year}年{mo-i}月5日(晴)</td>'
            f'<td>大井11R(ダート {dist}m)</td>'
            f'<td>{t}</td><td>前{front:.1f}-後{back:.1f}</td>'
            f'<td>3着</td></tr>')
    return "<html><body><table>" + "".join(rows) + "</table></body></html>"


def selftest():
    # (1) 合成データ: 後半垂れない馬 vs 失速馬。速度はほぼ同等。
    #   垂れない馬 = 前後半差ゼロ、失速馬 = 後半+1.5s。predictが垂れない馬を上位に。
    td = [("1.54.0", 1800)] * 5
    good = _synthetic_html(39.0, 39.0, td)   # late_drop 0.0
    bad = _synthetic_html(38.0, 39.5, td)    # late_drop +1.5
    field = [[1, "ジゾク号", "G"], [2, "シッソク号", "B"]]
    html_by_id = {"G": good, "B": bad}
    rows = predict(field, html_by_id)

    gm = next(r for r in rows if r["umaban"] == 1)
    bm = next(r for r in rows if r["umaban"] == 2)
    print(f"ジゾク号 : drop {gm['drop']:+.2f}s  速度n {gm['pace']:.2f}  "
          f"総合 {gm['total']:.1f}")
    print(f"シッソク号: drop {bm['drop']:+.2f}s  速度n {bm['pace']:.2f}  "
          f"総合 {bm['total']:.1f}")
    assert gm["drop"] < bm["drop"], "垂れない馬のdropが小さいはず"
    assert gm["sustain_n"] > bm["sustain_n"], "持続スコアの大小が逆"
    assert rows[0]["umaban"] == 1, f"垂れない馬が総合1位のはず: {[r['umaban'] for r in rows]}"
    # 速度がほぼ同等なので parse/metrics も健全か軽く確認
    assert abs(gm["pace"] - bm["pace"]) < 1e-6, "同タイム同距離なら速度は一致"
    print("合成: PASS（後半垂れない馬を総合上位に）")

    # (2) 実データが在れば predict→render が9頭ぶん例外なく動くか
    base = ("/tmp/claude-0/-home-user-keiba/"
            "c0647a9c-3b9e-5469-9601-35c8f135823e/scratchpad")
    fpath = os.path.join(base, "field1116.json")
    hdir = os.path.join(base, "kb")
    if os.path.exists(fpath) and os.path.isdir(hdir):
        with open(fpath, encoding="utf-8") as f:
            rfield = json.load(f)
        rrows = build(rfield, hdir, "/tmp/race_predict_demo.html",
                      title="大井11R オフト大郷賞 ダ1800m")
        assert len(rrows) == len(rfield), "出走頭数ぶん出ていない"
        got = sum(1 for r in rrows if r["m"] and r["m"]["n"] > 0)
        assert got == len(rfield), f"近走が取れない馬がある: {got}/{len(rfield)}"
        doc = open("/tmp/race_predict_demo.html", encoding="utf-8").read()
        assert "総合予想" in doc and "<table" in doc and "後半持続" in doc
        print(f"実データ: PASS（{len(rrows)}頭・各馬近走取得 OK）")
        print("HTML: /tmp/race_predict_demo.html")
        print("―― 総合上位 ――")
        for i, r in enumerate(rrows[:5], 1):
            print(f"  {i}. {r['umaban']}番 {r['name']:　<10} 総合{r['total']:5.1f}  "
                  f"速度{r['speed_n']:4.0f} 持続{r['sustain_n']:4.0f} "
                  f"後-前{r['drop']:+.2f}s")
    else:
        print("実データ無し: 合成のみでPASS")
    print("SELFTEST PASSED")


def main():
    ap = argparse.ArgumentParser(
        description="レースの総合予想（後半持続＋スピード指数）をHTML化")
    ap.add_argument("--field", help="出走馬リストJSON [[馬番,馬名,馬ID],...]")
    ap.add_argument("--htmldir", help="各馬の<馬ID>.htmlが入ったディレクトリ")
    ap.add_argument("-o", "--out", default="race.html")
    ap.add_argument("--title", default="レース")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.field or not args.htmldir:
        ap.error("--field と --htmldir を指定してください（または --selftest）")
    with open(args.field, encoding="utf-8") as f:
        field = json.load(f)
    rows = build(field, args.htmldir, args.out, title=args.title)
    print(f"保存: {args.out}（{len(rows)}頭）")
    print("―― 総合ランキング ――")
    for i, r in enumerate(rows, 1):
        tot = "  -  " if r["total"] is None else f"{r['total']:5.1f}"
        sp = " - " if r["speed_n"] is None else f"{r['speed_n']:3.0f}"
        su = " - " if r["sustain_n"] is None else f"{r['sustain_n']:3.0f}"
        dp = "  -  " if r["drop"] is None else f"{r['drop']:+.2f}s"
        print(f"  {i:2}. {r['umaban']:>2}番 {str(r['name']):　<10} "
              f"総合{tot}  速度{sp} 持続{su} 後-前{dp}")


if __name__ == "__main__":
    main()
