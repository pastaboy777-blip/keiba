# -*- coding: utf-8 -*-
"""ooi_fit.py の出した表を1枚の画像用HTMLにする。買う側だけ。

  python3 scripts/ana/ooi_fit_card.py <fit.md> <out.html>
"""
import html, json, os, re, sys

MD, OUT = sys.argv[1], sys.argv[2]
P = json.load(open(os.path.splitext(MD)[0] + '.json', encoding='utf-8'))

# 鞍ごとの壁と、鞍の中での並び
race, bar, rank, line = {}, {}, {}, {}
cur = None
for ln in open(MD, encoding='utf-8'):
    m = re.match(r'## (\d+)R　(\d+)m　(\d+)頭（水準 自前半([\d.]+)＋上り([\d.]+)', ln)
    if m:
        cur, n = m.group(1), 0
        race[cur] = dict(dist=int(m.group(2)), n=int(m.group(3)),
                         mh=float(m.group(4)), ma=float(m.group(5)))
    m = re.match(r'壁 \*\*([\d.]+)\*\*', ln)
    if m:
        bar[cur] = float(m.group(1))
    if ln.startswith('| ') and '**' in ln and cur:
        c = [x.strip() for x in ln.split('|')]
        n += 1
        rank[(cur, c[1])] = n
        line[(cur, c[1])] = dict(ph=c[4], pa=c[5], rec=c[8])

# 貼ってもらったカードと重なる馬
OVER = {'ゴーディアンノット', 'ショウナンカブト', 'ルカドリーマー'}
WHY = {
 'ダスマパーティ': '前走1200mを<b>37.5＋40.3</b>で9番人気5着。不良1200mの水準は'
               '<b>36.5＋39.3</b>。<b>上りの水準が1秒ぶん下りてくる</b>ので、'
               'この脚のままで足りる',
 'ソレイユダーム': '<b>37.6＋40.2</b>。ダスマパーティと同型で<b>置き直した時計は同値</b>。'
               '2Rはこの2頭で押さえたい',
 'ポロリス': '10番人気で負け続けている。前走1600mの<b>65.2＋41.0</b>は、'
            '不良1600mの水準<b>64.0＋40.9</b>とほぼ同じ。'
            '伸びなくても水準どおりで足りる',
 'ルカドリーマー': '139日ぶり。1400mの<b>51.2＋40.4</b>を1600mの水準に置き直すと3番手と同値。'
              '<b>鞍内3位</b>。4Rは上位3頭が0.3秒に収まる横一線',
 'ハッピーワイド': '前走<b>64.9＋41.3</b>で5着。自前半が水準より1秒速い側にある。'
                '前に行ける脚を持ったまま9番人気まで落ちた',
 'コロラドフォンテン': '前走1800mを<b>79.2＋39.3</b>。200m短くなって<b>鞍内1位</b>、'
                  '3番手に0.5秒の差',
 'ゴーディアンノット': '15走ぶん実測がある。1200mは4走して古い順に<b>2着・5着・7着・2着</b>、'
                 '最速上り37.2。<b>鞍内1位</b>で3番手に0.5秒の差',
 'ドレッドノート': '前走1400mで<b>49.5＋39.2</b>の3着。1200mに下りて自前半36.0は'
              '鞍内で最速クラス',
 'グリスタン': '2400mを<b>119.6＋42.0</b>まで走っている。1800mは<b>600mの短縮</b>。'
            '<b>鞍内2位</b>で3番手に0.9秒の差',
 'ショウナンカブト': '1600重で<b>64.2＋38.1</b>。この上りを2000mの水準に置くと<b>鞍内3位</b>。'
                '522kgでこの鞍の最重量クラス',
 'ムットクルフェ': '前走1400mを<b>48.4＋38.0</b>。2000mで<b>上りの水準が2.3秒下りる</b>',
}
G = {'◎': ('#d95926', '条件が下りてきた馬', '直近3走の人気が9番人気以下。今年の大井で 22.8%（同じ層の平均 8.1%）'),
     '○': ('#3987e5', '穴で押さえたい', '直近3走の人気が6〜8番人気。今年の大井で 32.7%（同じ層の平均 20.4%）')}

rows = {'◎': [], '○': []}
for p in sorted(P, key=lambda z: (z['R'], int(z['u']))):
    R = str(p['R'])
    k = (R, f"{p['mk']} {p['u']}")
    ln = line.get(k, {})
    rows[p['mk']].append(dict(p, rk=rank.get(k, 0), n=race[R]['n'],
                              ph=ln.get('ph', ''), pa=ln.get('pa', ''),
                              why=WHY.get(p['nm'], ''), over=p['nm'] in OVER))


def tbl(mk):
    c, ttl, sub = G[mk]
    h = [f'<section><div class="sh"><span class="badge" style="background:{c}">{mk}</span>'
         f'<h2>{ttl}</h2><span class="sub">{sub}</span></div>',
         '<table><thead><tr><th>R</th><th>番</th><th>馬名</th><th>距離</th>'
         '<th>鞍内</th><th>自前半</th><th>上り</th>'
         '<th>直近人気</th><th>買える理由</th></tr></thead><tbody>']
    for r in rows[mk]:
        L = r['last']
        ov = ('<span class="ov">貼ってもらったカードと重なる</span>' if r['over'] else '')
        dd = r['D'] - L['dist']
        ds = (f'{L["dist"]}<span class="ar">→</span>{r["D"]}'
              f'<br><span class="dm">{dd:+d}m</span>' if dd
              else f'{r["D"]}m<br><span class="dm">据え置き</span>')
        h.append(
            f'<tr style="--c:{c}"><td class="r">{r["R"]}R</td><td class="u">{r["u"]}</td>'
            f'<td class="nm">{html.escape(r["nm"])}{ov}</td>'
            f'<td class="d">{ds}</td>'
            f'<td class="rk"><b>{r["rk"]}</b>/{r["n"]}</td>'
            f'<td class="mono">{r["ph"]}</td><td class="mono">{r["pa"]}</td>'
            f'<td class="pp">{r["pp"]:g}人</td><td class="why">{r["why"]}</td></tr>')
    return '\n'.join(h) + '</tbody></table></section>'


HTML = f'''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#e8e6e3;font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
 padding:48px 56px 40px;width:1900px;-webkit-font-smoothing:antialiased}}
h1{{font-size:40px;font-weight:800;letter-spacing:.01em}}
h1 .ac{{color:#d95926}}
.tag{{display:inline-block;background:#d95926;color:#fff;font-size:15px;font-weight:700;
 padding:4px 12px;border-radius:5px;margin-left:14px;vertical-align:7px}}
.lead{{margin-top:18px;font-size:19px;line-height:1.85;color:#cfccc8;max-width:1760px}}
.lead b{{color:#fff;font-weight:700}}
.lead .hl{{color:#ff8a5c;font-weight:700}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:30px 0 8px}}
.tile{{background:#141412;border:1px solid #262622;border-radius:10px;padding:18px 20px}}
.tile .k{{font-size:13px;color:#8e8a84;letter-spacing:.04em}}
.tile .v{{font-size:38px;font-weight:800;margin-top:6px;line-height:1}}
.tile .v small{{font-size:19px;font-weight:700;color:#8e8a84;margin-left:8px}}
.tile .n{{font-size:13px;color:#8e8a84;margin-top:9px;line-height:1.55}}
section{{margin-top:38px}}
.sh{{display:flex;align-items:center;gap:13px;margin-bottom:14px}}
.badge{{width:30px;height:30px;border-radius:50%;color:#fff;font-size:17px;font-weight:800;
 display:flex;align-items:center;justify-content:center}}
h2{{font-size:25px;font-weight:800}}
.sub{{font-size:14px;color:#8e8a84;margin-left:4px}}
table{{width:100%;border-collapse:collapse}}
th{{font-size:13px;color:#8e8a84;font-weight:500;text-align:left;padding:0 12px 9px;
 border-bottom:1px solid #262622;letter-spacing:.04em}}
td{{padding:15px 12px;border-bottom:1px solid #1d1d1a;font-size:16px;vertical-align:top}}
tr td:first-child{{border-left:4px solid var(--c);padding-left:16px}}
.r{{color:#8e8a84;font-size:15px;width:52px}}
.u{{font-weight:800;font-size:21px;color:var(--c);width:44px}}
.nm{{font-weight:700;font-size:19px;width:210px}}
.ov{{display:block;font-size:11px;font-weight:600;color:#c98500;margin-top:5px;letter-spacing:.02em}}
.d{{width:132px;font-size:15px;font-weight:700;white-space:nowrap}}
.ar{{color:#6e6a64;margin:0 5px;font-weight:400}}
.dm{{font-size:12px;color:#8e8a84;font-weight:500}}
.rk{{width:84px;font-variant-numeric:tabular-nums;color:#8e8a84;font-size:17px}}
.rk b{{font-size:23px;font-weight:800;color:#e8e6e3}}
.mono{{width:84px;font-variant-numeric:tabular-nums;color:#b5b1ab}}
.pp{{width:84px;font-weight:700;color:var(--c)}}
.why{{color:#cfccc8;font-size:15px;line-height:1.7}}
.why b{{color:#fff}}
.vtiles{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}
.two{{display:grid;grid-template-columns:auto 1fr auto 1fr;align-items:baseline;
 gap:0 10px;margin-top:8px}}
.v2{{font-size:33px;font-weight:800;line-height:1;color:#c98500}}
.v2.dim{{color:#6e6a64}}
.v2 small{{font-size:17px;margin-left:3px}}
.lb{{font-size:12px;color:#8e8a84}}
.note{{margin-top:16px;font-size:16px;line-height:1.8;color:#cfccc8}}
.note b{{color:#fff}}
footer{{margin-top:36px;padding-top:22px;border-top:1px solid #262622;
 font-size:15px;line-height:1.85;color:#a5a19b}}
footer b{{color:#fff}}
footer .hl{{color:#ff8a5c;font-weight:700}}
</style></head><body>
<h1>10/27（火）大井 ── <span class="ac">普段の脚で足りる馬</span><span class="tag">今年の大井 915鞍で検証ずみ</span></h1>
<p class="lead">
10/26 の9Rは<b>エムオーナイナー（10番人気）</b>が勝った。上がりは <b>39.8</b>。この馬が1200mで8番手から使っていた上がりと
<b>同じ数字</b>。速くなったのは馬ではなくレースのほう。──だから探すのは「伸びそうな馬」ではなく、
<span class="hl">今日と同じ脚で足りる鞍</span>。<br>
距離×馬場ごとの水準（自前半・上り3Fの中央値）に、その馬の実測のズレをそのまま置き直す。
置き直した時計が<b>その鞍の3番手に届くか</b>だけを見る。<br>
ただし同じ距離・馬場でも、鞍によって走破時計が <b>3.6〜4.9秒</b> ちがう（1200mなら上位1割と下位1割で3.6秒。端どうしなら7.2秒）。
<span class="hl">上のクラスほど上りが速い</span>（上のクラスの鞍は水準より上り −1.03秒、下のクラスは +0.98秒）ので、
距離×馬場だけで測ると<b>クラスの速さを馬の脚として読んでしまう</b>。
絶対時計と鞍内偏差（クラスを抜いた相手との差）を<b>半々</b>で混ぜてある。
</p>
<div class="tiles">
 <div class="tile"><div class="k">鞍内3位以内</div><div class="v">42.2<small>%</small></div>
  <div class="n">全出走は 22.9%。6,959頭で測った</div></div>
 <div class="tile"><div class="k">直近人気 9番人気以下 × 鞍内3位以内</div>
  <div class="v" style="color:#d95926">22.8<small>%</small></div>
  <div class="n">同じ層の平均 8.1% ── <b>2.8倍</b>（クラス補正前は19.5%）</div></div>
 <div class="tile"><div class="k">直近人気 6〜8番人気 × 鞍内3位以内</div>
  <div class="v" style="color:#3987e5">32.7<small>%</small></div>
  <div class="n">同じ層の平均 20.4% ── <b>1.6倍</b></div></div>
 <div class="tile"><div class="k">10/26 を事前情報だけで走らせたら</div>
  <div class="v">4<small>/8頭 50%</small></div>
  <div class="n">当日の全出走は25%。<b>サンバフレイバー（9番人気1着）</b>を拾えた</div></div>
</div>
{tbl('◎')}
{tbl('○')}
<section><div class="sh"><span class="badge" style="background:#c98500">検</span>
<h2>貼ってもらったカードの選び方を測った</h2>
<span class="sub">今年の大井・前走のある 8,696頭</span></div>
<div class="vtiles">
 <div class="tile"><div class="k">間隔 30日以上</div>
  <div class="two"><span class="v2">34.1<small>%</small></span><span class="lb">全馬</span>
   <span class="v2 dim">10.0<small>%</small></span><span class="lb">6人気以下</span></div>
  <div class="n">全馬では <b>+10.0pt</b>。人気薄に絞ると <b>+0.9pt</b>。
   休ませてもらえる馬は期待されている馬なので、<b>人気で説明がついてしまう</b></div></div>
 <div class="tile"><div class="k">距離 ±200m 以上の変化</div>
  <div class="two"><span class="v2 dim">22.1<small>%</small></span><span class="lb">全馬</span>
   <span class="v2 dim">8.7<small>%</small></span><span class="lb">6人気以下</span></div>
  <div class="n">全馬 <b>−2.1pt</b>、人気薄 <b>−0.3pt</b>。短縮も延長も同じ。
   距離が動くこと自体には向きがない</div></div>
 <div class="tile"><div class="k">両方（±200m以上 × 30日以上）</div>
  <div class="two"><span class="v2">32.8<small>%</small></span><span class="lb">全馬</span>
   <span class="v2 dim">9.7<small>%</small></span><span class="lb">6人気以下</span></div>
  <div class="n">人気薄では <b>+0.6pt</b>。組み合わせても上積みはない</div></div>
</div>
<p class="note">8頭の事実関係（馬番・距離・前走距離・間隔・上り）は
<b>ほぼ全部そのとおり</b>だった。そのうち
<b>ゴーディアンノット・ショウナンカブト・ルカドリーマー</b>の3頭は、
この水準の置き直しでも鞍内3位以内に入る。上の表にそのまま入っている。
フラグランツァはクラス補正を入れると2番人気まで評価が上がり、妙味の側から外れた。</p>
</section>
<footer>
<b>前提がひとつ。</b>この形は<b>全体が遅くなる日</b>に出る。10/26 は12鞍すべて不良だった。<br>
後半のレースほど時計が速く見えるが、<span class="hl">それは馬場ではなくクラス</span>。
1〜6R は鞍のレベルが <b>+2.05</b>、7〜12R は <b>+0.43</b>。上りの差 <b>−0.73秒</b>は、
レベルの差 −1.62秒 × 0.45 ＝ −0.73秒 でちょうど説明がつく。
<b>馬場そのものが動いた証拠はない。</b>どちらの向きにも賭けない。<br>
「鞍内」は置き直した時計の鞍内順位。4位でも3番手と同値なら拾う（4R⑪ハッピーワイド）。
良に戻っても上の11頭はそのまま残る（鞍の全体が一緒に動くため）。<b>馬場待ちは不要。</b>
朝に馬場状態を取り直し、発走30分前にオッズで印を打ち直す。<br>
相手は <b>4〜6番人気</b>で埋めたい。10/26 は 2〜3番人気 29.2% に対して <b>4〜6番人気 36.1%</b> だった。
</footer>
</body></html>'''
open(OUT, 'w', encoding='utf-8').write(HTML)
print('書き出し', OUT, '◎', len(rows['◎']), '○', len(rows['○']))
