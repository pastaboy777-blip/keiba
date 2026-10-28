# -*- coding: utf-8 -*-
"""1日のラップを、ふだんの形と重ねて1枚にする。

  python3 scripts/ana/ooi_lap_card.py <lap.json> <YYYYMMDD> <開始R> <out.html>

横じくは1ハロンぶんの幅をどの鞍でも同じにして、ゴール側で右そろえ。
縦じくも全パネル共通なので、鞍をまたいで形がそのまま比べられる。
灰色の点線は今年の大井の同じ距離の中央値。
"""
import json, re, statistics as st, sys

LAPF, YMD, FROM, OUT = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')
C_DAY, C_REF = '#d95926', '#7a7670'
PXF = 38                      # 1ハロンぶんの横はば
LO, HI = 11.0, 14.3           # 縦じく（全パネル共通）
PT, PB, PLX, PRX = 16, 26, 34, 16
IH = 118

A = json.load(open(LAPF, encoding='utf-8'))
RS = [k for k in sorted(A, key=int) if int(k) >= FROM]

# ── ふだんの形（今年の大井・距離ごとの中央値）────────────────
L = {}
for l in open(f'{SP}/corners_2026.jsonl', encoding='utf-8'):
    x = json.loads(l)
    if x.get('lap'):
        L[x['rid']] = x['lap']
D = {}
for l in open(f'{SP}/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    lap = L.get(r['rid'])
    if lap and r.get('dist') and len(lap) == r['dist'] // 200:
        D.setdefault(r['dist'], []).append(lap)
REF = {d: [st.median([x[i] for x in v]) for i in range(d // 200)]
       for d, v in D.items() if len(v) >= 20}
NREF = {d: len(v) for d, v in D.items()}

# ── 走破時計（勝ち馬）──────────────────────────────────
WIN = {}
for l in open(f'{SP}/ooi_2026_runs.jsonl', encoding='utf-8'):
    r = json.loads(l)
    if r.get('ymd') == YMD and r.get('e'):
        WIN[int(r['rid'][-2:])] = (r['e'][0].get('tm'), r.get('baba'),
                                   r.get('n') or len(r['e']))


def y(v):
    return PT + IH * (HI - v) / (HI - LO)


def panel(k):
    v = A[k]
    lap, dist = v['lap'], v['dist']
    nf = len(lap)
    ref = REF.get(dist)
    W = PLX + PXF * nf + PRX
    H = PT + IH + PB
    fast = lap.index(min(lap))
    xs = [PLX + PXF * (i + 0.5) for i in range(nf)]

    g = []
    # 目もり
    for t in (12.0, 13.0, 14.0):
        g.append(f'<line x1="{PLX}" y1="{y(t):.1f}" x2="{W-PRX}" '
                 f'y2="{y(t):.1f}" stroke="#1f1f1c" stroke-width="1"/>')
        g.append(f'<text x="{PLX-7}" y="{y(t)+4:.1f}" text-anchor="end" '
                 f'fill="#6e6a64" font-size="11">{t:.0f}</text>')
    # ふだんの形
    if ref:
        pr = ' '.join(f'{x:.1f},{y(t):.1f}' for x, t in zip(xs, ref))
        g.append(f'<polyline points="{pr}" fill="none" stroke="{C_REF}" '
                 f'stroke-width="2" stroke-dasharray="5 4" opacity=".8"/>')
    # その日
    pd = ' '.join(f'{x:.1f},{y(t):.1f}' for x, t in zip(xs, lap))
    g.append(f'<polyline points="{pd}" fill="none" stroke="{C_DAY}" '
             f'stroke-width="2.5" stroke-linejoin="round"/>')
    for i, (x, t) in enumerate(zip(xs, lap)):
        r = 6.5 if i == fast else 5
        g.append(f'<circle cx="{x:.1f}" cy="{y(t):.1f}" r="{r}" '
                 f'fill="{C_DAY}" stroke="#0a0a0a" stroke-width="2"/>')
    # いちばん速い1本と、最後の1本だけ数字を出す
    for i in sorted({fast, nf - 1}):
        g.append(f'<text x="{xs[i]:.1f}" y="{y(lap[i])-13:.1f}" '
                 f'text-anchor="middle" fill="#e8e6e3" font-size="14" '
                 f'font-weight="700">{lap[i]:.1f}</text>')
    # 横じく（ゴールまでのハロン）
    for i in range(nf):
        rem = nf - i
        lab = 'ゴール' if rem == 1 else f'{rem-1}'
        g.append(f'<text x="{xs[i]:.1f}" y="{PT+IH+17}" text-anchor="middle" '
                 f'fill="#6e6a64" font-size="{10 if rem==1 else 11}">{lab}</text>')
    tm, baba, nh = WIN.get(int(k), ('', '', ''))
    d33 = v.get('lap33')
    return (f'<div class=pn style="width:{W+22}px">'
            f'<div class=hd><span class=rn>{k}<span class=rr>R</span></span>'
            f'<span class=dm>{dist}m・{baba}・{nh}頭</span>'
            f'<span class=wt>{tm}</span></div>'
            f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            + ''.join(g) + '</svg>'
            f'<div class=ft>前3F <b>{v["f3"]}</b>　上り3F <b>{v["ag3"]}</b>'
            f'　33ラップ <b>{d33:+.1f}</b></div></div>')


# ── まとめの表 ────────────────────────────────────────
rows = ''
for k in RS:
    v = A[k]
    ref = REF.get(v['dist'])
    rf3 = sum(ref[:3]) if ref else None
    ra3 = sum(ref[-3:]) if ref else None
    f = lambda a, b: (f'{a-b:+.1f}' if b is not None else '－')
    rows += (f'<tr><td class=k>{k}R</td><td class=d>{v["dist"]}m</td>'
             f'<td class=n>{v["f3"]:.1f}</td>'
             f'<td class=g>{f(v["f3"], rf3)}</td>'
             f'<td class=n>{v["ag3"]:.1f}</td>'
             f'<td class=g>{f(v["ag3"], ra3)}</td>'
             f'<td class=n>{v["lap33"]:+.1f}</td></tr>')

HTML = f'''<!doctype html><html lang=ja><head><meta charset=utf-8>
<title>ラップ</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:46px 52px 38px;width:1460px;-webkit-font-smoothing:antialiased}}
h1{{font-size:40px;font-weight:800}} h1 .ac{{color:#d95926}}
.lead{{margin-top:14px;font-size:17px;line-height:1.8;color:#cfccc8;max-width:1320px}}
.lead b{{color:#fff}}
.key{{display:flex;gap:28px;align-items:center;margin-top:20px;font-size:15px;color:#8e8a84}}
.key i{{display:inline-block;width:30px;height:0;border-top:3px solid;margin-right:9px;
 vertical-align:4px}}
.wrap{{display:flex;flex-wrap:wrap;gap:16px;margin-top:22px}}
.pn{{background:#121210;border:1px solid #1f1f1c;border-radius:12px;padding:13px 11px 11px}}
.hd{{display:flex;align-items:baseline;gap:10px;padding:0 6px 6px}}
.rn{{font-size:28px;font-weight:800;color:#d95926;font-variant-numeric:tabular-nums}}
.rr{{font-size:15px;opacity:.65;margin-left:2px}}
.dm{{font-size:13px;color:#8e8a84;font-weight:600}}
.wt{{margin-left:auto;font-size:16px;font-weight:700;color:#cfccc8;
 font-variant-numeric:tabular-nums}}
.ft{{padding:6px 6px 0;font-size:12.5px;color:#8e8a84;font-variant-numeric:tabular-nums}}
.ft b{{color:#cfccc8;font-size:14px}}
h2{{font-size:24px;font-weight:800;margin:36px 0 2px}}
h2 small{{font-size:14px;font-weight:500;color:#8e8a84;margin-left:12px}}
table{{border-collapse:collapse;margin-top:12px}}
th{{font-size:12px;color:#8e8a84;font-weight:500;text-align:right;padding:0 16px 7px;
 border-bottom:1px solid #262622}}
td{{padding:11px 16px;border-bottom:1px solid #1d1d1a;text-align:right;
 font-variant-numeric:tabular-nums}}
.k{{text-align:left;font-size:20px;font-weight:800;color:#d95926}}
.d{{text-align:left;color:#8e8a84;font-size:15px}}
.n{{font-size:21px;font-weight:700}}
.g{{font-size:16px;color:#8e8a84}}
footer{{margin-top:30px;padding-top:20px;border-top:1px solid #262622;
 font-size:15px;line-height:1.9;color:#a5a19b}}
footer b{{color:#fff}} footer .hl{{color:#ff8a5c;font-weight:700}}
</style></head><body>
<h1>10/28（水）大井　<span class=ac>{FROM}R〜{RS[-1]}R のラップ</span></h1>
<p class=lead>
横じくは<b>ゴールまでのハロン数</b>。1ハロンぶんの幅はどの鞍でも同じで、右端がゴール。
<b>縦じくも全パネル共通</b>なので、鞍をまたいで形がそのまま比べられる。
大きい丸がその鞍のいちばん速い1本。
</p>
<div class=key>
 <span><i style="border-color:{C_DAY}"></i>この日</span>
 <span><i style="border-color:{C_REF};border-top-style:dashed"></i>ふだん（今年の大井・同じ距離の中央）</span>
 <span>数字は秒</span>
</div>
<div class=wrap>{''.join(panel(k) for k in RS)}</div>

<h2>数字で見る<small>カッコの列は、ふだんとの差</small></h2>
<table><tr><th style="text-align:left">R</th><th style="text-align:left">距離</th>
<th>前3F</th><th>ふだん比</th><th>上り3F</th><th>ふだん比</th><th>33ラップ</th></tr>
{rows}</table>

<footer>
<b>33ラップ</b>＝「残り6〜3F」−「上り3F」。マイナスが大きいほど前が速くて持久戦、
0に近いほど上がり勝負。<br>
<b>2400mにふだんの線がない</b>のは、今年の大井でラップが取れているのが
{NREF.get(2400, 0)}鞍だけで、中央値が出せないため。
<span class=hl>12Rの形は、ふだんと比べずに見ること</span>。<br>
ふだんの線は、同じ距離で{min(NREF.get(d, 0) for d in (1200, 1400, 1600))}鞍以上をならした中央値。
</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
