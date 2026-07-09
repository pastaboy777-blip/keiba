# インフォグラフ雛形（X/note用）

前セッションで作った「変態か、変態以外か。」ブランドのインフォグラフ雛形。
scratchpadは毎セッション消えるので、再利用する雛形はここに保存する（引き継ぎメモの注記に対応）。

## ファイル
- `render.py` … HTML→PNGレンダラ。`python3 render.py input.html output.png [width]`
  - Playwright chromium `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`、device_scale_factor=2、フォント WenQuanYi Zen Hei。
  - 事前に `pip install playwright`（ブラウザは既存を使うので `playwright install` は不要）。
- `tegen_daymodel_tekijikan.html` … **鉄則16の時間帯スライド作戦**（前半41→後半40）の作戦ボード。
  レース番号→勝ち圏上がりの棒グラフ + 前半/後半の狙い方タイル + 実証コメント。
- `tegen_lap_kaibou.html` … **ラップ解剖**（実ラップ棒グラフ + 位置取り二層化 前40.9/後399 + 勝ち圏上がりの読み替え）。

## 配色テンプレ
背景 `#0f1f33` / アクセント 橙`#ff9e64`・黄`#ffd54a`・水`#5cc8e0`・緑`#7ee0a0`・警戒`#ff8a8a`。幅1120px。
上部にブランド帯、フッター右に **By Claude AI**。編集フィードバックは1項目ずつ来るので都度直して再送。

## 使い方
1. 対象レースのHTMLを雛形からコピーして数値・馬名を差し替え。
2. `python3 render.py <html> <png> 1120` でPNG化。
3. `SendUserFile` で送付。
