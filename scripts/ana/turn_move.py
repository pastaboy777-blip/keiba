# -*- coding: utf-8 -*-
"""Finishing Speed % と Turn Time を南関で測る。

  python3 scripts/ana/turn_move.py [場名...]

① Finishing Speed %（香港ジョッキークラブ方式）
     後半600mの速さ ÷ レース全体の平均の速さ × 100。
     比なので距離をまたいで比べられる。

② Turn Time（Brohamer ／ 米国ダート分析）
     前半3Fでも上がり3Fでもない、勝負どころの手前の3ハロン。

注意：1500mと1700mは最初の1本が100mしかない（6.8秒などと出る）。
ハロン数で距離を決めつけると、1500mを1600m扱いしてしまい、
平均の速さが実際より速く出て Finishing Speed % が5ポイント低く沈む。
ここでは 1本目の長さを 距離 −200×(本数−1) で出して揃える。
"""
import json, statistics as st, sys
from collections import defaultdict

BA = sys.argv[1:] or ['船橋']
SP = ('/tmp/claude-0/-home-user-keiba/a716475a-b623-5ff0-8a6c-762d20462748/'
      'scratchpad')


def segs(dist, lap):
    """各ハロンが何メートルか。1本目だけ短いことがある"""
    first = dist - 200 * (len(lap) - 1)
    return [first] + [200] * (len(lap) - 1)


def fs_pct(dist, lap):
    tot = sum(lap)
    if tot <= 0 or len(lap) < 4:
        return None
    last3 = sum(lap[-3:])
    return (600 / last3) / (dist / tot) * 100


def turn_time(dist, lap):
    """2〜4ハロン目。1本目が100mの距離では1つずらして本当の2〜4本目を取る"""
    sg = segs(dist, lap)
    i = 1 if sg[0] == 200 else 2
    v = lap[i:i + 3]
    return sum(v) if len(v) == 3 else None


R = [json.loads(l) for l in open(f'{SP}/nankan_2026.jsonl', encoding='utf-8')]
for ba in BA:
    rs = [r for r in R if r['ba'] == ba and r.get('lap') and r.get('dist')]
    print(f'■ {ba}　ラップのある {len(rs)}鞍\n')
    D = defaultdict(list)
    for r in rs:
        f = fs_pct(r['dist'], r['lap'])
        t = turn_time(r['dist'], r['lap'])
        if f:
            D[r['dist']].append((f, t, r))
    print('① Finishing Speed %（後半600m ÷ 全体平均 ×100）')
    print(f"{'距離':>7}{'鞍数':>6}{'中央値':>9}{'幅':>18}{'100%以上':>10}")
    for d in sorted(D):
        v = [x[0] for x in D[d]]
        if len(v) < 8:
            continue
        over = sum(1 for x in v if x >= 100)
        print(f'  {d}m{len(v):>6}{st.median(v):>8.1f}%'
              f'{min(v):>10.1f}〜{max(v):.1f}{over:>8}鞍')
    allv = [x[0] for v in D.values() for x in v]
    print(f'  ぜんぶ {len(allv)}鞍  100%未満が '
          f'{sum(1 for x in allv if x < 100)}鞍 '
          f'({100*sum(1 for x in allv if x<100)/len(allv):.0f}%)')

    print('\n② Turn Time（勝負どころの手前3ハロン）')
    print(f"{'距離':>7}{'鞍数':>6}{'中央値':>9}{'幅':>16}{'上がり3Fの幅':>14}")
    for d in sorted(D):
        v = [x[1] for x in D[d] if x[1]]
        a = [sum(x[2]['lap'][-3:]) for x in D[d]]
        if len(v) < 8:
            continue
        print(f'  {d}m{len(v):>6}{st.median(v):>8.1f}秒'
              f'{max(v)-min(v):>10.1f}秒差{max(a)-min(a):>12.1f}秒差')

    print('\n③ 終いが落ちた鞍と保った鞍で、4角先頭はどうなるか')
    for d in sorted(D):
        v = [x for x in D[d] if x[2].get('c4')]
        if len(v) < 40:
            continue
        m = st.median([x[0] for x in v])
        for lab, f in (('落ちた側', lambda z: z[0] < m), ('保った側', lambda z: z[0] >= m)):
            s = [x for x in v if f(x)]
            win = ins = tot = 0
            for _, _, r in s:
                c4 = r['c4']
                if not c4:
                    continue
                lead = c4[0]
                e = next((e for e in r['e'] if int(e['u']) == lead), None)
                if not e or not e.get('f', '').isdigit():
                    continue
                tot += 1
                win += e['f'] == '1'
                ins += int(e['f']) <= 3
            if tot >= 20:
                print(f'  {d}m {lab}（{tot}鞍）　4角先頭が '
                      f'1着 {100*win/tot:4.1f}% ／ 3着内 {100*ins/tot:4.1f}%')
    print()
