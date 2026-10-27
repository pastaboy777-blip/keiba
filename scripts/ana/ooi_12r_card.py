# -*- coding: utf-8 -*-
"""各レース 本命1頭・穴1頭 を1枚にする。

  python3 scripts/ana/ooi_12r_card.py <pick.json> <日付> <out.html>

本命は置き直した時計の鞍内1位（人気は見ない）。
穴は直近3走の人気が6番人気以下のうち、壁までの余裕がいちばん大きい馬。
"""
import html, json, sys

PICK, DAY, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
P = json.load(open(PICK, encoding='utf-8'))
BY = {}
for p in P:
    BY.setdefault(p['R'], {})[p['kind']] = p

C_H, C_A = '#3987e5', '#d95926'


def cell(p, c):
    if not p:
        return '<td colspan=7 class=none>人気薄の候補なし</td>'
    ds = (f"{p['pd']}<span class=ar>→</span>{p['dist']}" if p['pd'] and p['pd'] != p['dist']
          else f"{p['dist']}m")
    extra = (f'2位と<b>{p["lead"]:+.2f}</b>' if p['kind'] == '本命'
             else f'壁まで<b>{p["slack"]:+.2f}</b>')
    return (f'<td class=u style="--c:{c}">{p["uu"]}</td>'
            f'<td class=nm>{html.escape(p["nm"])}'
            f'<span class=si>{html.escape(p["sire"])}</span></td>'
            f'<td class=ex style="--c:{c}">{extra}</td>'
            f'<td class=rk><b>{p["rk"]}</b>/{p["nr"]}</td>'
            f'<td class=rk><b>{p["hrk"]}</b>/{p["nr"]}</td>'
            f'<td class=rk>{(str(p["ark"])+"/"+str(p["nar"])) if p.get("ark") else "－"}</td>'
            f'<td class=sm>{p["wt"] or "－"}<span class=un>kg</span></td>'
            f'<td class=pp>{p["pp"]:g}<span class=un>人</span><br>'
            f'<span class=un>{p["ppop"]}人{p["pf"]}着</span></td>')


# 脚注はその日の中身から組む
hon = [p for p in P if p['kind'] == '本命']
ana = [p for p in P if p['kind'] == '穴']
strong = [p for p in hon if p['lead'] >= 0.5]
flat = [p for p in hon if p['lead'] <= 0.05]
ok = [p for p in ana if p['slack'] >= 0.3]
even = [p for p in ana if 0 <= p['slack'] < 0.3]
nm = lambda v: '・'.join(f"{p['R']}R{chr(0x2460 + int(p['uu']) - 1)}{p['nm']}"
                         if int(p['uu']) <= 20 else f"{p['R']}R{p['uu']}{p['nm']}" for p in v)
FOOT = ('<b>本命の強さは「2位との差」で決まる。</b>'
        '差が0.5秒以上あれば3着内 <b>72.9%</b>・勝ち <b>40.1%</b>、0.2秒未満だと 45.5% まで落ちる。'
        + (f'この日 0.5秒以上は <b>{nm(strong)}</b>。' if strong
           else '<span class=hl>この日は0.5秒以上がひとつもない。</span>')
        + (f' 2位との差がない（横一線）のは {nm(flat)} で、ここは本命から入らない。' if flat else '')
        + '<br><b>穴は余裕0.3秒以上が条件（28.4%）。</b>'
        + (f'この日の該当は <b>{nm(ok)}</b>。' if ok
           else '<span class=hl>この日それを満たす穴はいない。</span>')
        + (f' 壁と同値（18.7%）が {nm(even)}。' if even else '')
        + ' 残りは届いていない。<b>穴は無理に全鞍買う形ではない。</b><br>')

rows = []
for R in sorted(BY):
    h, a = BY[R].get('本命'), BY[R].get('穴')
    d = h or a
    rows.append(
      f'<tr><td class=r>{R}R<br><span class=dm>{d["dist"]}m {d["n"]}頭</span></td>'
      + cell(h, C_H) + '<td class=gap></td>' + cell(a, C_A) + '</tr>')

HTML = f'''<!doctype html><html lang=ja><head><meta charset=utf-8>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:46px 54px 38px;width:2000px;-webkit-font-smoothing:antialiased}}
h1{{font-size:39px;font-weight:800}} h1 .b{{color:#3987e5}} h1 .a{{color:#d95926}}
.tag{{display:inline-block;background:#d95926;color:#fff;font-size:15px;font-weight:700;
 padding:4px 12px;border-radius:5px;margin-left:14px;vertical-align:7px}}
.lead{{margin-top:17px;font-size:19px;line-height:1.85;color:#cfccc8;max-width:1880px}}
.lead b{{color:#fff}} .lead .hl{{color:#ff8a5c;font-weight:700}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin:26px 0 6px}}
.tile{{background:#141412;border:1px solid #262622;border-radius:10px;padding:17px 19px}}
.tile .k{{font-size:13px;color:#8e8a84}}
.tile .v{{font-size:37px;font-weight:800;margin-top:5px;line-height:1}}
.tile .v small{{font-size:18px;color:#8e8a84;margin-left:5px}}
.tile .n{{font-size:13px;color:#8e8a84;margin-top:8px;line-height:1.55}}
table{{width:100%;border-collapse:collapse;margin-top:14px}}
th{{font-size:12px;color:#8e8a84;font-weight:500;text-align:left;padding:0 10px 8px;
 border-bottom:1px solid #262622}}
th.h{{color:#3987e5;font-size:17px;font-weight:800;padding-bottom:4px}}
th.a{{color:#d95926;font-size:17px;font-weight:800;padding-bottom:4px}}
td{{padding:13px 10px;border-bottom:1px solid #1d1d1a;font-size:16px;vertical-align:top}}
.r{{width:74px;color:#cfccc8;font-weight:700;font-size:17px}}
.dm{{font-size:12px;color:#8e8a84;font-weight:500}}
.u{{width:46px;font-weight:800;font-size:22px;color:var(--c);
 border-left:4px solid var(--c);padding-left:13px}}
.nm{{font-weight:700;font-size:18px;width:196px}}
.si{{display:block;font-size:12px;font-weight:500;color:#8e8a84;margin-top:4px}}
.ex{{width:118px;color:#8e8a84;font-size:14px;white-space:nowrap}}
.ex b{{color:var(--c);font-size:19px;font-variant-numeric:tabular-nums}}
.rk{{width:66px;color:#8e8a84;font-variant-numeric:tabular-nums;font-size:13px}}
.rk b{{font-size:18px;color:#e8e6e3}}
.sm{{width:84px;color:#b5b1ab;font-variant-numeric:tabular-nums;line-height:1.5}}
.un{{font-size:12px;color:#8e8a84;margin-left:2px}}
.pp{{width:76px;font-weight:700;color:#cfccc8;line-height:1.5}}
.gap{{width:30px;border-bottom:1px solid #1d1d1a}}
.none{{color:#6e6a64;font-size:15px}}
footer{{margin-top:30px;padding-top:20px;border-top:1px solid #262622;
 font-size:15px;line-height:1.85;color:#a5a19b}}
footer b{{color:#fff}} footer .hl{{color:#ff8a5c;font-weight:700}}
</style></head><body>
<h1>{DAY} 大井 ── 各レース <span class=b>本命</span>と<span class=a>穴</span>
<span class=tag>今年の大井 927鞍で検証ずみ</span></h1>
<p class=lead>
馬の脚は変わらないものとして置き、条件（距離×馬場）の水準だけを動かす。
<b class=b>本命</b>は置き直した時計の<b>鞍内1位</b>（人気は見ない）。
<b class=a>穴</b>は直近3走の人気が6番人気以下で、<b>壁までの余裕</b>がいちばん大きい馬。
</p>
<div class=tiles>
 <div class=tile><div class=k>見込み1位（本命）</div>
  <div class=v style="color:#3987e5">55.7<small>%</small></div>
  <div class=n>全体は 22.9%。勝ちは 24.4%</div></div>
 <div class=tile><div class=k>↑ 2位との差が0.5秒以上なら</div>
  <div class=v style="color:#3987e5">72.9<small>%</small></div>
  <div class=n>勝ちも <b>40.1%</b>（177鞍）</div></div>
 <div class=tile><div class=k>人気薄 × 鞍内3位以内（穴）</div>
  <div class=v style="color:#d95926">20.3<small>%</small></div>
  <div class=n>人気薄ぜんぶは 9.3%</div></div>
 <div class=tile><div class=k>↑ かつ 壁まで0.3秒以上の余裕</div>
  <div class=v style="color:#d95926">28.4<small>%</small></div>
  <div class=n>壁とほぼ同値だと 18.7% に落ちる</div></div>
</div>
<table><thead><tr><th></th><th class=h colspan=2>本命</th>
<th>2位との差</th><th>鞍内</th><th>自前半</th><th>上り</th><th>馬体重</th><th>直近／前走</th>
<th></th><th class=a colspan=2>穴</th>
<th>壁までの余裕</th><th>鞍内</th><th>自前半</th><th>上り</th><th>馬体重</th><th>直近／前走</th>
</tr></thead><tbody>{''.join(rows)}</tbody></table>
<footer>
{FOOT}
馬場は良で置いた。朝に取り直し、<b>1〜3鞍走ってから</b>以降の3着ラインを直す。
発走30分前にオッズで印を打ち直す。
</footer></body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT)
