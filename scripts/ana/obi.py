"""直線の図を3つの帯に分けて、本線・押さえ・消しを出す（2026-11-17、ユーザーの手順）。

  python3 obi.py <card.json> --ven 大井 [--R 1-12] [--odds odds.json] \
      [--cyokyo c.json] [--res res.json] [--swap 6:12-1] [--pos-nama] [--choku-median]
      [--wakeru [--pace R:S R:M … --pace-obi]]

★★ 2026-11-17 統合で変えたこと（2つ）
  ① **帯は図に描いた横位置で切る**（`tenkai_zu.narabi()` ＋ `tenkai_zu.obi_bands()` をそのまま呼ぶ）。
     図の既定は順位で等間隔（rankify）なので**順位で3等分**、`--pos-nama` のときは**値で 1/3・2/3**。
     `tenkai_zu.py --chokusen --obi` の色帯と**全頭一致**する（同じ関数）。
     以前は pos4w の値を 1/3・2/3 で切っていたので、図の見た目の帯とずれる馬がいた。
  ② **既定は前の帯と中の帯を分けない**。ユーザー確定（2026-11-17）──「**分けないで**」。
     （別セッションのルール66「前の帯と中の帯は分けない」と同じ考え）
       本線   … 前の帯・中の帯 × 終い3位以内
       押さえ … 前の帯・中の帯 × 終い札なし（終い4位以下・順位なし）
       消し   … 後ろの帯 × 終い札なし
       後ろ・終いあり … 後ろの帯 × 終い3位以内（どれにも当たらない残り）
       帯なし … 過去走なし（pos が測れない馬）。**消さない**（ルール6・22）。図では鞍の中ほどに置く馬
     これまでの「軸候補＝前・相手＝中」に分ける形は **`--wakeru`** を付けたときだけ。
     `--pace-obi` は **`--wakeru` の形の上でだけ**効く（`--wakeru` なしでは何も変えない）。

★ ユーザーが示した手順（2026-11-17・そのまま引用。③は `--wakeru` の形）

  ① 2枚目（直線の図）を3等分して帯を作る。
  ② 「終い◯位」の札が3位以内の馬だけ拾う。1鞍あたり約2頭。
  ③ 前の帯のものが軸候補、中の帯のものが相手。
  ④ 後ろの帯で終い札なしは全部消す。1鞍あたり2.8頭が消え、そこから来たのは31頭中2頭。

★ 値は新しく計算しない。`tenkai_zu.narabi()`（図と同じ並べ方）をそのまま呼ぶ。
  直線の位置 … `pos4w`（直線の盤面 `--chokusen` と同じ、4角相対の直近重みづけ 5,4,3,2,1。0が前。
               `--choku-median` で中央値）。図の横はその**順位**（`--pos-nama` なら値そのまま）
  終い順位   … 図の「終い◯位」と同じ決め方（`tenkai_zu.main` の srank ── その鞍の全馬の
               `l` を昇順に並べて1から番号。`l` が無い馬は順位なし。同値は出馬表の並び順）。
               出馬表に載っている馬（取消を含む）で数える ── 図と同じ。

★ 帯の切り方 … 上の★★①（図に描いた横位置。統合前は pos4w の値を 1/3・2/3 で切っていた）

★ 分け方（`--wakeru` のとき）
  軸候補 … 前の帯で終い3位以内
  相手   … 中の帯で終い3位以内
  消し   … 後の帯で終い3位以内でない馬
  残り   … 上のどれでもない馬（前・中の帯で終い札なし、後の帯で終い札あり）と、帯なしの馬

★ 帯なし … 過去走なし（図で pos が仮置きの馬・`nopos`）。図では鞍の中ほどに描かれるので
  図の上の帯は付くが、測った位置ではないので判定には使わない。
  **消さない**（CLAUDE.md ルール6「履歴が引けない馬を切らない」・ルール22「過去走のない馬を
  図から消さない」）。既定では「帯なし」、`--wakeru` では「残り」に入れる。

★ 付記（判定には使わない）
  人気   … `--odds`（tenkai_zu と同じ形 {R:[{ub,nin,..}]}）か出馬表の nin。無ければ `--res` の人気欄。
  調教☝ … `--cyokyo` を渡したとき、`tenkai_zu.cyk_fuda()` が '調教↑' の馬。

★ `--res` … 2つの形を読む。
  ① 競馬ブックの結果（`sei*.json`）── {R: {meta:..., rows:[{ub:'6', chaku:1, nin:'2', ...}]}}
  ② 簡単な形 ── {R: {馬番: 着順}}
  着順が無い馬（取消など）は数えから外す。
  渡すと各馬に着順を付け、鞍ごとに「軸候補・相手・消し・残り」から何頭3着内に来たかと、全鞍の合計を出す。

★ `--pace R:S R:M R:H ...` と `--pace-obi`（2026-11-17 に足した**試しの口**。既定ではない。
  **`--wakeru` の形の上でだけ効く**。`--wakeru` なしでは渡しても何も変わらない）
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
GRP = ('本線', '押さえ', '消し', '後ろ・終いあり', '帯なし')       # 既定（分けない）
GRP_W = ('軸候補', '相手', '消し', '残り')                          # --wakeru
OBI_NM = {'前': '前', '中': '中', '後': '後ろ'}


def mb(ub):
    return MARU[ub - 1] if 1 <= ub <= len(MARU) else '(%d)' % ub


def grp_of(o, sr, nopos):
    """既定（分けない。ユーザー確定 2026-11-17「分けないで」）"""
    if nopos:
        return '帯なし'
    shimai = sr is not None and sr <= 3
    if o in ('前', '中'):
        return '本線' if shimai else '押さえ'
    return '後ろ・終いあり' if shimai else '消し'


def grp_wakeru(o, sr, nopos, jiku='前', aite='中'):
    """--wakeru（統合前の既定。軸候補＝前・相手＝中）"""
    if nopos:
        return '残り'
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


def setup(a):
    """図（`tenkai_zu.py --chokusen`）と同じ口で並べるための設定。
    tenkai_zu は import した同じモジュールなので、前に走った図の設定が残らないよう全部置き直す。"""
    Z.CHOKU = True
    Z.CHOKU_MEDIAN = '--choku-median' in a
    Z.POS_NAMA = '--pos-nama' in a
    Z.POS_MEDIAN = '--pos-median' in a
    Z.POS_MAZERU = '--pos-mazeru' in a
    Z.OLD_C4 = ('--c4' in a) or ('--old' in a)
    Z.OLD_NOMB = ('--nomb' in a) or ('--old' in a)
    Z.SWAPDU = '--swapdu' in a
    Z.NOPAST_CENTER = '--nopast-center' in a


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith('-'):
        print(__doc__)
        return
    g = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    setup(a)
    ven = g('--ven', '大井')
    lo, _, hi = g('--R', '1-12').partition('-')
    lo, hi = int(lo), int(hi or lo)
    od_all = json.load(open(g('--odds'))) if g('--odds') else {}
    cyk = Z.load_cyokyo(g('--cyokyo'))
    res = load_res(g('--res'))
    swap_sp = {k: v.split(',') for k, v in Z.kv(a, '--swap', pairs=True).items()}
    C = json.load(open(a[0]))
    wakeru = '--wakeru' in a
    # --pace / --pace-obi（2026-11-17 の試しの口。--wakeru の形の上でだけ効く）
    pace_obi = wakeru and '--pace-obi' in a
    pace = {k: v.upper() for k, v in Z.kv(a, '--pace').items()} if pace_obi else {}
    groups = GRP_W if wakeru else GRP

    tot = {k: [0, 0] for k in groups}          # [頭数, 3着内]
    tot_obi = {k: [0, 0] for k in ('前', '中', '後', 'なし')}
    nR, n_shimai, n_kesi = 0, 0, 0
    for key in sorted(C, key=lambda x: C[x]['R']):
        v = C[key]
        if not (lo <= v['R'] <= hi):
            continue
        R = str(v['R'])
        od = {o['ub']: o for o in (od_all.get(R) or [])}
        sw = [tuple(int(y) for y in p_.split('-')) for p_ in swap_sp.get(R, [])]
        rows = Z.narabi(v, ven, od, sw, '--noswap' in a)     # 図と同じ並び・同じ pos
        band, bp, _ = Z.obi_bands(rows)                       # 図と同じ帯
        rv = res.get(R, {})
        cz = cyk.get(R, {})
        pc = pace.get(R)
        jiku, aite = ('中', '前') if (pace_obi and pc == 'S') else ('前', '中')
        for k_, r in enumerate(rows, 1):
            r['zui'] = k_                                     # 図の前からの順番
            r['obi'] = band.get(r['ub'])
            r['grp'] = (grp_wakeru(r['obi'], r['srank'], r['nopos'], jiku, aite) if wakeru
                        else grp_of(r['obi'], r['srank'], r['nopos']))
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
        title = '%sR  %s%dm  %s  %d頭' % (R, ven, v['dist'], v.get('cls', ''), len(rows))
        if pace_obi:
            if pc == 'S':
                pz = 'ペースS（ペース版：軸＝中の帯・相手＝前の帯）'
            elif pc in ('M', 'H'):
                pz = 'ペース%s（ペース版：今の手順と同じ　軸＝前の帯・相手＝中の帯）' % pc
            else:
                pz = 'ペース%s（ペース版：未指定のため今の手順　軸＝前の帯・相手＝中の帯）' % (pc or 'なし')
            title += '  ' + pz
        print(title)
        for gname in groups:
            gs = [r for r in rows if r['grp'] == gname]       # 図の前からの順
            ins = sum(1 for r in gs if r['chaku'] and r['chaku'] <= 3)
            cnt = sum(1 for r in gs if not r['torikesi'])
            head = '  %s（%d頭' % (gname, cnt)
            head += '・3着内%d）' % ins if rv else '）'
            print(head + ('　' + ' '.join(mb(r['ub']) for r in gs) if gs else '　なし'))
            for r in gs:
                s = '    %s %-12s 図%2d番目 帯%-2s ' % (mb(r['ub']), r['name'], r['zui'],
                                                     OBI_NM.get(r['obi'], '-'))
                s += ('pos4w %.2f' % r['pos4w']) if r.get('pos4w') is not None else '過去走なし'
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
            k = 'なし' if r['nopos'] else (r['obi'] or 'なし')
            tot_obi[k][0] += 1
            tot_obi[k][1] += bool(r['chaku'] and r['chaku'] <= 3)

    print('=' * 64)
    print('合計（%d鞍・取消は除く）' % nR + ('　※ --wakeru（軸候補＝前・相手＝中に分ける形）' if wakeru else '')
          + ('　※ --pace-obi（ペース版・試しの口）' if pace_obi else ''))
    print('  終い3位以内 %d頭（1鞍あたり %.2f頭）' % (n_shimai, n_shimai / nR if nR else 0))
    print('  消し       %d頭（1鞍あたり %.2f頭）' % (n_kesi, n_kesi / nR if nR else 0))
    for k in groups:
        print('  %-6s %3d頭' % (k, tot[k][0]) + ('  3着内 %d' % tot[k][1] if res else ''))
    if res:
        print('  （帯ごと）' + '　'.join('%s %d頭中%d' % ({'後': '後ろ', 'なし': '帯なし'}.get(k, k), *tot_obi[k])
                                    for k in tot_obi))


if __name__ == '__main__':
    main()
