# -*- coding: utf-8 -*-
"""調教から「ズブさが薄れている馬」を拾う。

  python3 scripts/ana/zubu_fade.py <dayrank.txt> [--to-r 5]

ユーザーの定義（2026/11/08）
  「開催間隔が1ヶ月空いているから、たとえば馬也で3本乗られているのとか」

ズブい馬は、一杯に追ってようやく動く。
反応が戻っている馬は、追わなくても動く。だから見るのは時計そのものではなく
「どれだけ軽い追いで、どれだけ上位の時計を出したか」。

拾う条件（3つとも、その日の出走馬全体の中で相対化する）
  ① 軽さ   脚色の負荷が低い（馬なり0・稍強め2 まで）
  ② 本数   乗り込まれている（本数が多いほど加点）
  ③ 位置   それでいて、その日の順位が上のほう

③が核心。負荷0で「その日 2/13」なら、追わずに全体上位ということ。
逆に負荷4で「その日 36/36」なら、一杯に追ってなお最下位＝ズブいまま。

dayrank.txt の1行の形
  番 馬名  日付 コース 馬場 ／ 脚色 (負荷n) ／ 追組 a/b ／ その日 c/d ／ 同脚色 e/f ／ n本

時計そのものは出さない（CLAUDE.md）。順位と脚色だけ。
"""
import re
import sys

SRC = sys.argv[1]
TO_R = int(sys.argv[sys.argv.index('--to-r') + 1]) if '--to-r' in sys.argv else 12
FROM_R = int(sys.argv[sys.argv.index('--from-r') + 1]) if '--from-r' in sys.argv else 1

ROW = re.compile(
    r'^\s*(\d+)\s+(\S+?)\s+(\d\d/\d\d)\s+(\S+)\s+(\S+)\s*／\s*(\S+?)\s*'
    r'\(負荷([\d.]+)\)\s*／\s*(\S+)\s+(\d+)/(\d+)\s*／\s*その日\s+(\d+)/(\d+)\s*'
    r'／\s*同脚色\s+(\d+)/(\d+)\s*／\s*(\d+)本')

races, cur, head = {}, None, ''
for line in open(SRC, encoding='utf-8'):
    m = re.match(r'^■\s*(\d+)R\s+(\S+)\s*──\s*(\d+)頭', line)
    if m:
        cur = int(m.group(1))
        races[cur] = dict(cond=m.group(2), n=int(m.group(3)), e=[])
        continue
    if line.startswith('■'):
        head = head or line.strip()
        continue
    if cur is None:
        continue
    g = ROW.match(line)
    if not g:
        continue
    races[cur]['e'].append(dict(
        u=int(g.group(1)), nm=g.group(2), date=g.group(3),
        course=g.group(4), baba=g.group(5), ashi=g.group(6),
        load=float(g.group(7)), grp=g.group(8),
        gi=int(g.group(9)), gn=int(g.group(10)),
        di=int(g.group(11)), dn=int(g.group(12)),
        si=int(g.group(13)), sn=int(g.group(14)),
        hon=int(g.group(15))))

print(head)
print('\n■ ズブさが薄れている ── 軽い追いで、その日の上位にいる馬')
print('   ① 負荷2以下（馬なり・稍強め）  ② 本数が多い  ③ その日の順位が上位1/3\n')

hit_all = []
for R in sorted(races):
    if not (FROM_R <= R <= TO_R):
        continue
    r = races[R]
    ok = []
    for e in r['e']:
        if e['dn'] < 3:
            continue
        pos = (e['di'] - 1) / (e['dn'] - 1)        # 0が最上位
        if e['load'] <= 2 and pos <= 1 / 3:
            e['pos'] = pos
            ok.append(e)
    print(f"■ {R}R {r['cond']} ── {r['n']}頭"
          + ('' if ok else '　該当なし'))
    for e in sorted(ok, key=lambda x: (-x['hon'], x['load'], x['pos'])):
        print(f"   {e['u']:>2}番 {e['nm']:<14}"
              f"{e['ashi']:<6}／ その日 {e['di']}/{e['dn']:<4}"
              f"／ 同脚色 {e['si']}/{e['sn']:<4}／ {e['hon']}本"
              f"　{e['date']} {e['course']}{e['baba']}")
        hit_all.append((R, e))
    print()

print(f'■ 該当 {len(hit_all)}頭 / {len([R for R in races if FROM_R<=R<=TO_R])}鞍')
if hit_all:
    hon = [e['hon'] for _, e in hit_all]
    print(f'   本数の内訳 ' + '・'.join(
        f'{k}本 {hon.count(k)}頭' for k in sorted(set(hon))))
    print(f'   うち馬なり（負荷0） {sum(1 for _, e in hit_all if e["load"] == 0)}頭')
