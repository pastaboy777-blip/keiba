"""直線の図を3つの帯に分けて、軸候補・相手・消しを出す（2026-11-17、ユーザーの手順）。

  python3 obi.py <card.json> --ven 大井 [--R 1-12] [--odds odds.json] \
      [--cyokyo c.json] [--res res.json]

★ ユーザーが示した手順（2026-11-17・そのまま引用）

  ① 2枚目（直線の図）を3等分して帯を作る。
  ② 「終い◯位」の札が3位以内の馬だけ拾う。1鞍あたり約2頭。
  ③ 前の帯のものが軸候補、中の帯のものが相手。
  ④ 後ろの帯で終い札なしは全部消す。1鞍あたり2.8頭が消え、そこから来たのは31頭中2頭。

★ 値は新しく計算しない。`tenkai_zu.row_of()` をそのまま呼ぶ。
  直線の位置 … `pos4w`（直線の盤面 `--chokusen` と同じ、4角相対の直近重みづけ 5,4,3,2,1。0が前）
  終い順位   … 図の「終い◯位」と同じ決め方（`tenkai_zu.main` の srank ── その鞍の全馬の
               `l` を昇順に並べて1から番号。`l` が無い馬は順位なし。同値は出馬表の並び順）。
               出馬表に載っている馬（取消を含む）で数える ── 図と同じ。

★ 帯の切り方（図の横を3等分 ＝ 値で3等分）
  前 … 0 ≦ pos4w < 1/3 ／ 中 … 1/3 ≦ pos4w < 2/3 ／ 後 … 2/3 ≦ pos4w

★ 分け方
  軸候補 … 前の帯で終い3位以内
  相手   … 中の帯で終い3位以内
  消し   … 後の帯で終い3位以内でない馬
  残り   … 上のどれでもない馬（前・中の帯で終い札なし、後の帯で終い札あり）と、帯なしの馬

★ 帯なし … pos4w が None（4角の過去走が1本も無い＝過去走なし・転入初戦など）。
  **消さない**（CLAUDE.md ルール6「履歴が引けない馬を切らない」・ルール22「過去走のない馬を
  図から消さない」）。「残り」に入れて「帯なし（読めない）」と書く。

★ 付記（判定には使わない）
  人気   … `--odds`（tenkai_zu と同じ形 {R:[{ub,nin,..}]}）か出馬表の nin。無ければ `--res` の人気欄。
  調教☝ … `--cyokyo` を渡したとき、`tenkai_zu.cyk_fuda()` が '調教↑' の馬。

★ `--res` … 2つの形を読む。
  ① 競馬ブックの結果（`sei*.json`）── {R: {meta:..., rows:[{ub:'6', chaku:1, nin:'2', ...}]}}
  ② 簡単な形 ── {R: {馬番: 着順}}
  着順が無い馬（取消など）は数えから外す。
  渡すと各馬に着順を付け、鞍ごとに「軸候補・相手・消し・残り」から何頭3着内に来たかと、全鞍の合計を出す。

★ `--pace R:S R:M R:H ...` と `--pace-obi`（2026-11-17 に足した**試しの口**。既定ではない）
  --pace-obi は 2026-11-17 の1日だけを見て足した試しの口。既定ではない。使うかどうかはユーザーが決める。
  `--pace` の書き方は tenkai_zu.py の --pace と同じ（大文字小文字どちらでも）。ペースは**前日に図で
  付けた想定**を渡す（実際のペースは前日には分からない）。
  `--pace-obi` が無いときは `--pace` を渡しても何も変わらない（出力は1バイトも変わらない）。
  `--pace-obi` があるとき、鞍のペースで軸候補と相手の帯を入れ替える。
    S（スロー想定）… 軸候補＝中の帯×終い3位以内、相手＝前の帯×終い3位以内
    H（ハイ想定）  … 軸候補＝前の帯×終い3位以内、相手＝中の帯×終い3位以内（＝今の手順と同じ）
    M・未指定      … 今の手順と同じ
  消し（後の帯×終い札なし）はどのペースでも同じ。帯なしは消さない。
  各鞍の見出しに「ペースS（ペース版：軸＝中の帯）」のように使ったペースを書く。
  根拠は 11/17 大井1日の観察だけ（スローの鞍の1着は中の帯5・前の帯1、ハイの9〜12Rは不良の特別戦で
  前の帯が9頭。馬場・クラスと分けられていない）。

※ 見るのは渡したカードの日だけ（CLAUDE.md 最優先ルール）。何日ぶんもまとめる道具ではない。
"""
import sys, os, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tenkai_zu as Z

MARU = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱'
GRP = ('軸候補', '相手', '消し', '残り')


def mb(ub):
    return MARU[ub - 1] if 1 <= ub <= len(MARU) else '(%d)' % ub


def obi_of(p):
    if p is None:
        return None
    return '前' if p < 1 / 3 else ('中' if p < 2 / 3 else '後')


def grp_of(o, sr, jiku='前', aite='中'):
    shimai = sr is not None and sr <= 3
    if o == jiku and shimai:
        return '軸候補'
    if o == aite and shimai:
        return '相手'
    if o == '後' and not shimai:
        return '消し'
    return '残り'


def load_res(path):
    """{R: {ub(int): (着順 or None, 人気 or None)}}"""
    if not path:
        return {}
    J = json.load(open(path))
    out = {}
    for R, v in J.items():
        d = {}
        if isinstance(v, dict) and 'rows' in v:
            for x in v['rows']:
                try:
                    ub = int(x['ub'])
                except (TypeError, ValueError):
                    continue
                c = x.get('chaku')
                c = c if isinstance(c, int) else None
                n = x.get('nin')
                d[ub] = (c, int(n) if str(n or '').isdigit() else None)
        elif isinstance(v, dict):
            for k, c in v.items():
                d[int(k)] = (c if isinstance(c, int) else None, None)
        out[str(R)] = d
    return out


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith('-'):
        print(__doc__)
        return
    g = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    ven = g('--ven', '大井')
    lo, _, hi = g('--R', '1-12').partition('-')
    lo, hi = int(lo), int(hi or lo)
    od_all = json.load(open(g('--odds'))) if g('--odds') else {}
    cyk = ({R_: {h['ub']: h for h in hs} for R_, hs in json.load(open(g('--cyokyo'))).items()}
           if g('--cyokyo') else {})
    res = load_res(g('--res'))
    C = json.load(open(a[0]))
    # --pace / --pace-obi（2026-11-17 の試しの口。--pace-obi が無ければ何もしない）
    pace_obi = '--pace-obi' in a
    pace = {k: v.upper() for k, v in Z.kv(a, '--pace').items()} if pace_obi else {}

    tot = {k: [0, 0] for k in GRP}          # [頭数, 3着内]
    tot_obi = {k: [0, 0] for k in ('前', '中', '後', 'なし')}
    nR, n_shimai, n_kesi = 0, 0, 0
    for key in sorted(C, key=lambda x: C[x]['R']):
        v = C[key]
        if not (lo <= v['R'] <= hi):
            continue
        R = str(v['R'])
        od = {o['ub']: o for o in (od_all.get(R) or [])}
        rows = [Z.row_of(h, v['dist'], od, ven) for h in v['horses']]
        # 終い順位 ── tenkai_zu.main と同じ（l の昇順・l なしは順位なし）
        for i, r in enumerate(sorted([x for x in rows if x['l'] is not None],
                                     key=lambda x: x['l']), 1):
            r['srank'] = i
        rv = res.get(R, {})
        cz = cyk.get(R, {})
        pc = pace.get(R)
        jiku, aite = ('中', '前') if (pace_obi and pc == 'S') else ('前', '中')
        for r in rows:
            r.setdefault('srank', None)
            r['obi'] = obi_of(r['pos4w'])
            r['grp'] = grp_of(r['obi'], r['srank'], jiku, aite)
            c, n = rv.get(r['ub'], (None, None))
            r['chaku'] = c
            r['torikesi'] = bool(rv) and c is None
            r['nin_'] = r.get('nin') or n
            h = cz.get(r['ub'])
            r['cyk'] = bool(h) and Z.cyk_fuda(h) == '調教↑'
        nR += 1
        live = [r for r in rows if not r['torikesi']]
        n_shimai += sum(1 for r in live if r['srank'] is not None and r['srank'] <= 3)
        n_kesi += sum(1 for r in live if r['grp'] == '消し')

        print('=' * 64)
        if pace_obi:
            if pc == 'S':
                pz = 'ペースS（ペース版：軸＝中の帯・相手＝前の帯）'
            elif pc in ('M', 'H'):
                pz = 'ペース%s（ペース版：今の手順と同じ　軸＝前の帯・相手＝中の帯）' % pc
            else:
                pz = 'ペース%s（ペース版：未指定のため今の手順　軸＝前の帯・相手＝中の帯）' % (pc or 'なし')
            print('%sR  %s%dm  %s  %d頭  %s' % (R, ven, v['dist'], v.get('cls', ''), len(rows), pz))
        else:
            print('%sR  %s%dm  %s  %d頭' % (R, ven, v['dist'], v.get('cls', ''), len(rows)))
        for gname in GRP:
            gs = sorted([r for r in rows if r['grp'] == gname],
                        key=lambda r: (r['pos4w'] is None, r['pos4w'] if r['pos4w'] is not None else 9))
            ins = sum(1 for r in gs if r['chaku'] and r['chaku'] <= 3)
            cnt = sum(1 for r in gs if not r['torikesi'])
            head = '  %s（%d頭' % (gname, cnt)
            head += '・3着内%d）' % ins if rv else '）'
            print(head + ('　' + ' '.join(mb(r['ub']) for r in gs) if gs else '　なし'))
            for r in gs:
                s = '    %s %-12s ' % (mb(r['ub']), r['name'])
                s += ('pos4w %.2f 帯%s' % (r['pos4w'], r['obi'])) if r['obi'] else '帯なし（読めない）'
                s += '  終い%s' % ('%d位' % r['srank'] if r['srank'] else 'なし')
                if r['nin_']:
                    s += '  %s人気' % r['nin_']
                if r['cyk']:
                    s += '  ' + Z.CYK_LABEL
                if rv:
                    s += '  → ' + ('取消（数えない）' if r['torikesi'] else '%d着' % r['chaku'])
                print(s)
            tot[gname][0] += cnt
            tot[gname][1] += ins
        for r in live:
            k = r['obi'] or 'なし'
            tot_obi[k][0] += 1
            tot_obi[k][1] += bool(r['chaku'] and r['chaku'] <= 3)

    print('=' * 64)
    print('合計（%d鞍・取消は除く）' % nR + ('　※ --pace-obi（ペース版・試しの口）' if pace_obi else ''))
    print('  終い3位以内 %d頭（1鞍あたり %.2f頭）' % (n_shimai, n_shimai / nR if nR else 0))
    print('  消し       %d頭（1鞍あたり %.2f頭）' % (n_kesi, n_kesi / nR if nR else 0))
    for k in GRP:
        print('  %-4s %3d頭' % (k, tot[k][0]) + ('  3着内 %d' % tot[k][1] if res else ''))
    if res:
        print('  （帯ごと）' + '　'.join('%s %d頭中%d' % (k, *tot_obi[k]) for k in tot_obi))


if __name__ == '__main__':
    main()
