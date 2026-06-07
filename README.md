# nankeiba — 南関競馬 回収率特化 予測パイプライン

南関競馬(大井・川崎・船橋・浦和)の三連複・三連単を、**回収率(ROI)で勝つ**
ことを目的に設計した予測パイプライン。

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

## ラップ分析(楽天競馬から自動取得)

開催済みレースの**ハロンタイム(200mごとのラップ)**を楽天競馬から取得し、
コーナー区間ラベル付き・200m換算グラフ付きで分析する。出力は表形式のHTMLと
ターミナル表示。netkeiba 等が遮断される環境でも楽天競馬(keiba.rakuten.co.jp)は
到達できることを確認している。

```bash
pip install -r requirements.txt   # requests が必要

# 例: 5/18(月) 大井 9R〜12R を自動取得して分析
python3 scripts/lap_analyze.py --date 2026-05-18 --place 大井 --races 9-12

# 全レース
python3 scripts/lap_analyze.py --date 2026-05-18 --place 大井 --races all

# ネット不可の環境: ハロンタイムを手入力して分析(offline)
python3 scripts/lap_analyze.py --offline --distance 1600 \
    --laps "12.7-11.6-13.5-13.3-12.0-13.1-12.7-13.3" \
    --place 大井 --race-no 11 --date 2026-05-18 --going 良
```

- 出力: `out/lap_<日付>_<場>.html`(緑ヘッダの表 + コーナー区間色分け + 200m換算の折れ線)。
- 算出値: テン3F / 上がり3F(公式値優先)/ 前後半 / 平均ハロン / 最速・最遅区間 /
  ペース判定(ハイ・ミドル・スロー)と前後傾バランス。
- コーナー区間ラベルは大井の標準コース構成に基づく**目安**(1600m=8ハロンで
  「スタート〜1C…直線」に一致)。
- 分析ロジック(`analysis/lap.py`・`analysis/render.py`)は標準ライブラリのみ。
  取得部(`scraping/rakuten.py`)のみ requests を使用。

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
  analysis/    ラップ分析(標準ライブラリのみ)
    lap.py          ハロンタイム→区間分析・ペース判定
    render.py       表+200m換算グラフ(テキスト/HTML+inline SVG)
  scraping/    データ収集(netkeiba 地方・楽天競馬・ローカル実行)
    rakuten.py      楽天競馬の成績(ラップ)取得・パース
scripts/       demo / train / collect_data / lap_analyze
tests/         単体テスト
```
