# -*- coding: utf-8 -*-
"""東スポ「温故知新」170本から、馬名ごとの言及箇所を索引にする。

  python3 scripts/ana/onko_index.py [--min 3] [--name サウスヴィグラス]

本文はリポジトリに入れない（notes/onko/*.txt は .gitignore）。
出すのは索引だけで、引用は言及文のみに絞る。
"""
import json, glob, os, re, sys, collections

ARG = sys.argv[1:]


def opt(k, d=None):
    return ARG[ARG.index(k) + 1] if k in ARG else d


MIN = int(opt('--min', 3))
PICK = opt('--name')

KANA = re.compile(r'[ァ-ヶー]{4,14}')

# 馬名でない片仮名語（手で潰す）
STOP = set("""
インブリード アウトブリード ニックス クロス ブルードメア スタミナ スピード
バランス タイプ イメージ レベル パターン テーマ ポイント ファクター
セールスポイント スプリンター ステイヤー マイラー クラシック ダービー
オークス スプリント ダート コース ペース ラップ タイム
サラブレッド ヨーロッパ アメリカ イギリス フランス アイルランド オーストラリア
ケンタッキー ダービー オークション セレクト セール ジャッジ
ファイナルジャッジ シンジケート スタッフ トレセン ジョッキー トレーナー
クラブ コメント インタビュー ランキング シリーズ ステップ ステージ
パーセント キログラム センチ メートル ハロン
ノーザンダンサー系 サンデーサイレンス系 ミスタープロスペクター系
エクリプス ファミリー ライン ナンバー
オープン グレード ハンデ ローテ ローテーション
ゲート スタート ラスト ゴール
プラス マイナス ベスト ワースト
シルエット シャープ ソフト パワー
""".split())

arts = {}
for p in sorted(glob.glob('notes/onko/*.txt')):
    aid = os.path.basename(p)[:-4]
    txt = open(p, encoding='utf-8').read()
    ls = txt.split('\n')
    title = ls[0].lstrip('# ').strip()
    url = ls[1].lstrip('# ').strip()
    date = next((x.strip() for x in ls[2:8] if re.match(r'^\d{4}/', x.strip())), '')
    body = '\n'.join(ls[6:])
    arts[aid] = dict(title=title, url=url, date=date, body=body)

# 文に割る
SPL = re.compile(r'(?<=[。？！])')
sent = collections.defaultdict(list)   # 馬名 -> [(aid, 文)]
cnt = collections.Counter()
for aid, a in arts.items():
    seen_in_art = set()
    for line in a['body'].split('\n'):
        line = line.strip().replace('　', ' ')
        if not line:
            continue
        for s in SPL.split(line):
            s = s.strip()
            if len(s) < 6:
                continue
            for m in set(KANA.findall(s)):
                if m in STOP or m.endswith('系'):
                    continue
                sent[m].append((aid, s))
                seen_in_art.add(m)
    for m in seen_in_art:
        cnt[m] += 1          # 言及した記事の本数

if PICK:
    print(f'## {PICK}  ── 記事 {cnt.get(PICK,0)}本 / 言及 {len(sent.get(PICK,[]))}箇所\n')
    for aid, s in sent.get(PICK, []):
        print(f'- [{arts[aid]["date"][:10]}] {s}')
        print(f'    {arts[aid]["url"]}')
    sys.exit()

out = {m: dict(arts=cnt[m], hits=len(sent[m]),
               ids=sorted({a for a, _ in sent[m]}),
               lines=[[a, s] for a, s in sent[m]])
       for m in cnt if cnt[m] >= MIN}
json.dump(dict(meta={a: dict(title=v['title'], url=v['url'], date=v['date'])
                     for a, v in arts.items()},
               names=out),
          open('notes/onko/_index.json', 'w', encoding='utf-8'),
          ensure_ascii=False)
print(f'記事 {len(arts)}本 / 片仮名語 {len(cnt)} / {MIN}本以上に出る語 {len(out)}')
for m, c in cnt.most_common(40):
    print(f'{c:4d}本 {len(sent[m]):5d}箇所  {m}')
