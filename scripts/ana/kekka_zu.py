"""結果から展開図を起こす ── 1角→4角の位置と、併走したときの内外。

  python3 kekka_zu.py <res.json> <R> <出力.html> [--odds odds.json]

★ 事前の図と違って、**ここでは内外を書いてよい**。
  通過順の括弧は内→外の順なので、併走した馬については本物の内外が取れる。

★ ただし **単独だった馬の内外は記録されていない**（2026-11-10 川崎は136頭中80頭が単独）。
  「ラチ沿いを走った」と「併走の内にいた」は別のこと。単独は「単」と出して、
  内外を推測しない。CLAUDE.md ルール14。
"""
import sys, os, json, re, html

HERE = os.path.dirname(os.path.abspath(__file__))
WAKU = {1: ('#ffffff', '#111'), 2: ('#1b1b1b', '#fff'), 3: ('#e03a30', '#fff'),
        4: ('#2d6fd0', '#fff'), 5: ('#f2d231', '#111'), 6: ('#2f9e57', '#fff'),
        7: ('#f08a24', '#111'), 8: ('#f29ab8', '#111')}


def parse(raw):
    """通過順の生文字列 → [[内..外], ...]（順位グループ）"""
    out = []
    for m in re.finditer(r"\(([^)]*)\)|(\d+)", raw or ""):
        if m.group(1):
            out.append([int(x) for x in m.group(1).split(",")])
        else:
            out.append([int(m.group(2))])
    return out


def posmap(raw):
    """馬番 → (順位, 内外タグ)"""
    d, rank = {}, 0
    for g in parse(raw):
        for i, u in enumerate(g):
            d[u] = (rank + i + 1,
                    "単" if len(g) == 1 else ("内" if i == 0 else
                                              "外" if i == len(g) - 1 else "中"))
        rank += len(g)
    return d


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0c0c0e;color:#f2f2f4;width:1060px;padding:32px 38px 34px;
 font-family:"Noto Sans CJK JP","Hiragino Sans","Yu Gothic",sans-serif}
.head{border-bottom:2px solid #e8362f;padding-bottom:13px;margin-bottom:16px}
.kicker{color:#e8362f;font-size:13px;letter-spacing:.14em;font-weight:700}
h1{font-size:30px;font-weight:800;margin:5px 0 6px}
.sub{color:#8c8c96;font-size:12.8px;line-height:1.8}.sub b{color:#f2f2f4}
table{width:100%;border-collapse:collapse;background:#16161a;
 border:1px solid #2a2a31;border-radius:10px;overflow:hidden}
th{background:#121216;font-size:11.5px;color:#8c8c96;font-weight:700;
 padding:9px 6px;border-bottom:1px solid #2a2a31;letter-spacing:.04em}
td{padding:8px 6px;border-bottom:1px solid #22222a;font-size:13px;text-align:center}
tr.in3 td{background:#1d2318}
tr.in3 .ch{color:#5fe07a;font-weight:800}
.ch{font-size:15px;font-weight:800;width:46px}
.nm{text-align:left;font-size:12.5px;font-weight:700;white-space:nowrap}
.n{display:inline-block;min-width:22px;height:22px;line-height:22px;border-radius:50%;
 border:2px solid rgba(255,255,255,.45);font-size:12px;font-weight:800;margin-right:5px}
.c{font-size:14px;font-weight:800}
.t{display:inline-block;font-size:9.5px;font-weight:800;border-radius:3px;
 padding:0 4px;margin-left:3px;vertical-align:middle}
.t-in{background:#5fe07a;color:#0c0c0e}
.t-out{background:#ff9f52;color:#0c0c0e}
.t-mid{background:#9fb6cf;color:#0c0c0e}
.t-solo{color:#6a6a74;border:1px solid #3a3a44}
.dim{color:#8c8c96;font-size:11.5px}
.up{color:#5fe07a;font-weight:800}.dn{color:#e58b86;font-weight:800}
.note{margin-top:14px;background:#16161a;border:1px solid #2a2a31;
 border-left:3px solid #3987e5;border-radius:8px;padding:12px 16px;
 font-size:12.8px;line-height:1.9;color:#c9c9d2}
.note b{color:#f2f2f4}
.tail{margin-top:12px;font-size:11px;color:#5f5f69;line-height:1.7}
"""


def main():
    a = sys.argv[1:]
    if len(a) < 3:
        print(__doc__); return
    res, R, out = a[0], a[1], a[2]
    od = {}
    if "--odds" in a:
        O = json.load(open(a[a.index("--odds") + 1]))
        od = {o["ub"]: o for o in O.get(str(R), [])}
    v = json.load(open(res))[str(R)]
    raw = v.get("corner_raw") or {}
    M = {c: posmap(raw.get(c)) for c in ("1", "2", "3", "4")}
    rows = sorted(v["rows"], key=lambda r: r.get("chaku") or 99)
    note = a[a.index("--note") + 1] if "--note" in a else ""

    def cell(ub, c):
        p = M[c].get(ub)
        if not p:
            return '<td class="dim">―</td>'
        cls = {"内": "t-in", "外": "t-out", "中": "t-mid", "単": "t-solo"}[p[1]]
        return ('<td><span class="c">%d</span>'
                '<span class="t %s">%s</span></td>' % (p[0], cls, p[1]))

    tr = []
    for r in rows:
        ub = r["ub"]
        o = od.get(ub, {})
        p1 = M["1"].get(ub); p4 = M["4"].get(ub)
        mv = (p1[0] - p4[0]) if (p1 and p4) else None
        wc = WAKU.get(r.get("waku"), ('#15110d', '#f2f2f4'))
        tr.append('<tr class="%s"><td class="ch">%s</td>'
                  '<td class="nm"><span class="n" style="background:%s;color:%s">%d</span>%s</td>'
                  '%s%s%s%s'
                  '<td class="%s">%s</td><td>%s</td><td class="dim">%s</td><td class="dim">%s</td></tr>'
                  % ("in3" if (r.get("chaku") or 99) <= 3 else "",
                     ("%d着" % r["chaku"]) if r.get("chaku") else "―",
                     wc[0], wc[1], ub, html.escape(r["name"]),
                     cell(ub, "1"), cell(ub, "2"), cell(ub, "3"), cell(ub, "4"),
                     "up" if (mv or 0) > 0 else ("dn" if (mv or 0) < 0 else "dim"),
                     ("%+d" % mv) if mv is not None else "―",
                     r.get("agari") or "―",
                     ("%s人気 %s倍" % (o["nin"], o["odds"])) if o else "―",
                     ("%d%s" % (r["w"], r.get("dw") or "")) if r.get("w") else "―"))

    open(out, "w").write(
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<title>結果から起こした展開図</title><style>%s</style></head><body>'
        '<div class="head"><div class="kicker">2026.11.10 TUE — 川崎 ／ 馬場 不良</div>'
        '<h1>%dR %dm %d頭 ── 結果から起こした展開</h1>'
        '<div class="sub">通過順の括弧は<b>内→外の順</b>なので、'
        '<b>併走した馬は本物の内外</b>が取れます。'
        '<span class="t t-in">内</span><span class="t t-out">外</span>'
        '<span class="t t-mid">中</span> がそれ。'
        '<span class="t t-solo">単</span> は<b>単独で、内外は記録されていません</b> —— '
        'ラチ沿いだったかどうかは、ここからは分かりません。<br>'
        '「1→4角」は1コーナーから4コーナーでいくつ前へ出たか。</div></div>'
        '<table><tr><th>着</th><th style="text-align:left">馬</th>'
        '<th>1角</th><th>2角</th><th>3角</th><th>4角</th>'
        '<th>1→4角</th><th>上がり</th><th>単勝</th><th>馬体重</th></tr>%s</table>'
        '%s<div class="tail">印は買い目の保証ではありません。</div></body></html>'
        % (CSS, v["R"], v["dist"], len(v["rows"]), "\n".join(tr),
           ('<div class="note">%s</div>' % note) if note else ""))
    print(out)


if __name__ == "__main__":
    main()
