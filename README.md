# nankeiba — 南関競馬 回収率特化 予測パイプライン

南関競馬(大井・川崎・船橋・浦和)の三連複・三連単を、**回収率(ROI)で勝つ**
ことを目的に設計した予測パイプライン。

> 📰 **競馬新聞スタイルの「指数＆展開予想」**も生成できます → [下の専用セクション](#-指数展開予想新聞スタイル)。
> `python3 scripts/paper_demo.py` で新聞レイアウトの HTML を出力(`out/paper_demo.html`)。

## コンセプト:「ズブい馬をいかに走らせるか」

南関は全場が小回り・短い直線のダート、かつ開催頻度が高く、馬は出走間隔を
詰めて(連闘・中1週など)使われる。体質がズブい=タフな馬は短間隔でも崩れず、
むしろ使われ続けて調子を維持する。逆に間隔が空く(休み明け)とズブくて動かない。

つまり南関は **「ズブい馬を、陣営が手を尽くして今日のレースで走らせにいくゲーム」**。
能力そのものより「**今日その馬が走らせられているか**」を読む。そして世間(オッズ)は
派手な末脚や直近着順・人気を過大評価し、地味な間隔・叩き・条件替わりを軽視しがち
——その**市場の歪み**を突くのが回収率の勝ち筋。

### 「走らせる」を定量化する観点

| 観点 | 内容 | 実装 |
|------|------|------|
| 出走間隔フィット | 短間隔有利の全体傾向 + 馬ごとの間隔別成績 | `core/interval.py` |
| タフネス指数 | 出走頻度 × 短間隔での成績維持度(=ズブさ) | `core/interval.py` |
| 叩き良化 | 休み明けからの叩き○走目(2〜3走目がピーク) | `core/features.py` |
| 乗り替わり | 上位騎手への強化乗り替わりを加点 | `core/features.py` |
| 騎手の追える力 | ズブい馬を反応させて伸ばせる騎手か | `core/features.py` |
| 厩舎の仕上げ手腕 | 馬を「走らせる状態」に持ってくる厩舎か | `core/features.py` |
| 競馬場替わり/距離変更 | その馬に合う舞台・距離への転戦か | `core/features.py` |
| 使い込み疲労 | 詰めすぎの反動(タフネスの裏返し) | `core/features.py` |

## パイプライン全体像

```
① データ収集   netkeiba 地方 から 結果/オッズ を取得(src/nankeiba/scraping)
② 特徴量/スコア 「走らせる」観点を合算した強さスコア(core/features.py)
③ 確率変換     Plackett-Luce で 三連複/三連単 の的中確率(core/probability.py)
④ 期待値判定   確率 × オッズ > 閾値 の買い目だけ購入(core/betting.py)
⑤ バックテスト 時系列・リーク無しで回収率を検証(core/backtest.py)
```

**的中率 ≠ 回収率**: 人気馬を買えば的中率は上がるが、控除率(三連単 約27.5%)で
長期的に負ける。本パイプラインは的中率が低くても**期待値プラスの買い目だけ**を買い、
回収率100%超を狙う。

## クイックスタート

依存なし(標準ライブラリのみ)でロジックを確認:

```bash
python3 scripts/demo.py            # 合成データでエンドツーエンド・デモ
python3 scripts/train.py           # データから重みを学習し、未来レースで検証
python3 -m unittest discover -s tests -v
```

デモは南関の合成シーズンを生成し、「観点ありEVモデル」と「素朴な人気順買い」の
回収率を比較する。合成データでは市場が間隔・叩きを軽視する盲点を再現しており、
観点ありモデルがそれを突けることを示す。

> ⚠️ **重要**: 合成データは「コードとロジックが正しく機能すること」の検証用。
> 合成上のエッジは小さく乱数に敏感で、実戦の利益を保証しない。
> **必ずリアルデータでバックテストし、重み・閾値を検証・チューニングすること。**

## リアルデータの取得 → 学習 → 検証(ローカル実行)

ネットワークが必要なため、ローカル環境で実行する:

```bash
pip install -r requirements.txt

# 1) netkeiba 地方から「結果 + 三連複/三連単オッズ」を収集(JSONL 出力)
python3 scripts/collect_data.py --year 2024 --place 大井 --out data/results.jsonl
python3 scripts/collect_data.py --year 2024 --place 川崎 --out data/results.jsonl
#   …船橋・浦和・複数年ぶん集めるほど精度が上がる

# 2) 収集データから学習 → 検証(時系列分割・回収率を表示)
python3 scripts/build_dataset.py --data data/results.jsonl --bet-type trio
```

データの流れ:
```
collect_data.py ──(JSONL)──▶ core/dataset.py ──(Race)──▶ learn.py / backtest.py
```

- 収集の JSONL 形式は `core/dataset.py` の冒頭を参照(結果 + オッズ + 馬番)。
- 騎手・厩舎の勝率は `dataset.derive_conn_stats` が**学習区間だけ**から推定(リーク防止)。
- `src/nankeiba/scraping/client.py` はレート制限(既定1.5秒間隔)とキャッシュ付き。
- **節度を持って利用すること**: アクセス間隔を空け、robots.txt と各サイトの
  利用規約を尊重し、個人利用の範囲にとどめる。

### ⚠️ セレクタ/エンドポイントは要確認

netkeiba は HTML 構造や API を変えることがあるため、本環境(ネット遮断)では
実サイトに対する検証ができていない。次のファイルは実データを見て調整が必要:

- `scraping/parser.py` … 結果テーブルの CSS セレクタ・td 列インデックス
- `scraping/odds.py` … 三連複/三連単オッズの API URL と type コード

> 結果ページ/オッズの HTML(または JSON)サンプルを共有してもらえれば、
> 正確なセレクタ・パース処理を実装できる。`data/cache/` に保存された生 HTML が使える。

## データから重みを学習する

手設定の重み(`ScoreWeights` の既定値)に頼らず、**過去レースの着順から各観点の
重みを自動で学習**できる。

```python
from nankeiba.core.learn import train_scorer
from nankeiba.core.backtest import run_backtest

# 時系列で前半=学習・後半=検証(リーク無し)
scorer = train_scorer(train_races, jockeys=jockeys, trainers=trainers,
                       epochs=60, lr=0.2, l2=1e-3, top_k=3)
for name, w in scorer.importances():
    print(name, round(w, 3))          # 特徴量重要度(標準化済み係数)

res = run_backtest(test_races, score_fn=scorer, bet_type="trio")  # 学習重みで検証
```

- **学習モデル**: 各馬を特徴量ベクトルにし、線形スコア `s = w·x` を与える。
  レース着順は **Plackett-Luce** に従うとして、観測着順の対数尤度を勾配上昇で
  最大化する(=予測に使う確率モデルと同一で整合的)。`core/learn.py`
- 特徴量は学習データで標準化し、推論時も同じ統計量を使う(`LearnedScorer`)。
- `top_k=3` で「上位3着の説明力」を最大化(三連系に直結)。
- **共線性に注意**: 出走間隔と叩き良化は相関するため、個々の係数の符号は
  不安定になりうる(joint の予測は妥当)。`l2` を上げると安定する。
- **非線形版(任意)**: `core/learn_lgbm.py` は LightGBM の lambdarank で
  非線形な相互作用(短間隔×叩き2走目で特に走る、等)を学習できる。
  `LgbmScorer` は `score_fn` 互換。要 `pip install lightgbm numpy`。

`scripts/train.py` が学習→重要度表示→検証(既定重み vs 学習重み)の一連を実演する。

## 重み・閾値のチューニング

- `core/features.py` の `ScoreWeights` で各観点の重みを手調整。
- `core/interval.py` の `INTERVAL_PRIOR` は南関の全体傾向プライア。
  リアルデータで間隔バケット別の実成績を集計し、学習値で上書きするのが望ましい。
- `core/betting.py` の `ev_threshold` を上げると点数は減るが過信への保険になる。
- 検証は必ず**時系列分割**で(`backtest.run_backtest` は過去走のみ使用=リーク無し)。

## 次の拡張候補

- 間隔バケット別・叩き走目別の実成績から `INTERVAL_PRIOR`/`tatakii_bonus` を学習
- 騎手・厩舎の「追える力/仕上げ手腕」を実データの好走率から推定
- LightGBM(lambdarank)等で強さスコアを学習し、ヒューリスティックと比較
- ケリー基準(`select_ev_bets(kelly=True)`)での資金配分シミュレーション

## ディレクトリ構成

```
src/nankeiba/
  core/        核心ロジック(標準ライブラリのみ・テスト可能)
    interval.py     出走間隔・タフネス
    features.py     「走らせる」総合スコア(重み×特徴量)
    probability.py  Plackett-Luce 確率変換
    betting.py      期待値ベース買い目選定
    backtest.py     時系列バックテスト(ROI)
    learn.py        重み学習(Plackett-Luce 尤度最大化・標準ライブラリ)
    learn_lgbm.py   重み学習(LightGBM lambdarank・任意)
    synth.py        検証用 合成データ生成
    hindex.py       スピード指数(タイム指数)エンジン ★新聞用
    pace.py         展開予想「3走以内の通過順」6マスグリッド ★新聞用
    summary.py      指数系サマリー(10走以内/同競馬場/前3F) ★新聞用
    newspaper.py    新聞レイアウトの組み立て＋HTML/テキスト出力 ★新聞用
  scraping/    データ収集(netkeiba 地方・ローカル実行)
scripts/       demo / train / collect_data / paper_demo / build_paper
tests/         単体テスト
```

---

## 📰 指数＆展開予想(新聞スタイル)

実物の南関競馬新聞(マキシマム競馬新聞)の紙面を PDF から逆解析し、その中核である
**スピード指数**と**展開予想「3走以内の通過順」**を再現・自動生成する。出力は
新聞レイアウトの HTML(とテキスト)。

```bash
python3 scripts/paper_demo.py            # 合成データ→ out/paper_demo.html
python3 scripts/paper_demo.py --text     # テキストも表示

# 実データ(明日の大井など)から作る:
python3 scripts/build_paper.py data/sample_entries.json --out out/oi.html --text
python3 scripts/build_paper.py entries.json --corpus data/results.jsonl  # 指数校正を強化
```

### 指数の正体 = スピード指数(西田式ベース)

紙面の指数を逆解析した結論:

```
指数 = (基準タイム − 走破タイム) × 距離係数 + 馬場差 + 基準値
```

- **逆解析の根拠**(大井のサンプル): 大井1600の同一馬4走が
  `指数 ≒ 410.5 − 4.0×タイム秒` にほぼ完全一致(残差<0.5)。→ タイムに一次線形、
  **1600mで4.0点/秒**。距離が短いほど点/秒は大(タイム差が詰まるため)。
- 同タイムでも**馬場(良/稍/重/不)と開催日**で指数が上下(濡れた馬場ほど時計が
  速く出る=基準も速い)。→ 馬場差補正あり。
- **競馬場ごとに基準が違う**(大井は速い=同タイムでも辛い、浦和は遅い)。
- 値が負中心なのは、基準タイムを「強い時計」に置いているため(弱いレースは負)。

基準タイム表・馬場差は本来その新聞の非公開定数だが、`hindex.SpeedIndexModel.fit()`
が**データから自己校正**する(スピード指数の作り方そのもの)。データが無くても南関の
デフォルト基準タイムで概算できる。`distance_coef`/`going_offset`/`base` は調整可能。

### 展開予想「3走以内の通過順」6マスグリッド

各馬の過去3走以内のコーナー通過順を、着順(5着以内/6着以降)と位置取りで6マスに
振り分ける(`core/pace.py`)。

| | 5着以内だった走 | | | 6着以降だった走 | |
|--|--|--|--|--|--|
| 逃げ | 3・4角3番手以内 | 4角3番手以内 | 4角4番手以降 | 逃げ | 3・4角3番手以内 |

- 同じ馬が複数回同じマスに出ても1回だけ・馬番順・1マス最大10頭(超過は非表示)。
- **使い方**: 能力上位馬と同じマスの他馬は潰されやすい→相手は別マスから拾う。
  左2マス(5着以内の逃げ・先行)が手薄なら前残り想定(人気薄の逃げ先行も警戒)。

### 実データの入力形式

`scripts/build_paper.py` に渡す JSON は `data/sample_entries.json` を雛形に。
1レース分の `header`(場・距離・馬場・発走など)と、各馬の `history`(過去走を
新しい順)を入れる。過去走に `time_sec`(走破タイム秒=10進表記, 例 1:45.8→105.8)が
あれば指数が付き、`corner_pos`(コーナー通過順)があれば展開グリッドに載る。
netkeiba の結果テーブルをコピペして正規化する `ingest/pasted.py` も利用可
(走破タイム対応済み)。
