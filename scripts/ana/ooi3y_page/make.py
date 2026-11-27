"""ooi_keikou.py の --json 出力から、大井3年分の傾向ページ（HTML）を作る。
  python3 make.py <keikou.json> <out.html>
★ 人気は ooi_keikou.fix_nin で nk から戻したもの（2026-11-27。最後の行以外の nk は単勝人気そのもの）。
"""
import json, sys
d = json.load(open(sys.argv[1]))
DIST = ['1200m', '1400m', '1600m', '1650m', '1800m', '2000m', '1000m', '2400m']
BABA = ['良', '稍重', '重', '不良']
P = {
  'span': d['span'], 'days': d['days'], 'races': d['races'],
  'choku': d['choku_pos'], 'start': d['start_pos'],
  'cfrom': d['choku_from'], 'sfrom': d['start_from'],
  'lap': d['lap'], 'combo': d['combo'], 'side': d['side'], 'waku': d['waku'],
  'jk': {k: v for k, v in d['jockey'].items() if v['n'] >= 300},
  'year': d['year_choku'], 'nin': d['ninki_3nai'], 'nobi': d['ninki_obi'], 'dist': DIST, 'baba': BABA,
}
html = open(__file__.replace('make.py', 'tmpl.html')).read()
html = html.replace('/*DATA*/null', json.dumps(P, ensure_ascii=False, separators=(',', ':')))
open(sys.argv[2], 'w').write(html)
print(len(html), 'bytes')
