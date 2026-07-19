# パドック歩様解析ツール — 使い方ガイド

パドック動画1本から、**全頭を自動で分割 → 歩様を数値化 → 気配スコアでランキング → 骨格確認動画**まで生成します。

## 何ができる？
| ツール | 役割 |
|---|---|
| `run_paddock.py` | **これ1本で全部**（下の4つを順に実行) |
| `paddock_segment.py` | 馬番テロップOCRで全頭に自動分割 |
| `paddock_gait.py` | 各馬の歩様を数値化（目的馬ロック付き） |
| `skeleton_overlay.py` | 骨格線＋背骨(緑)＋重心(赤)の確認動画 |
| `paddock_compare.py` | 全頭を気配スコアで横並び比較(HTML) |

歩様指標: ストライド頻度/長さ、リズム安定、頭の上下動、背中の安定、重心。
**気配スコア**＝ストライドの伸び(後肢の踏み込み・推進力)を主役に合成した相対指標。

---

## セットアップ（自分のPC・初回のみ）

### 1. Python パッケージ
```bash
pip install -r requirements-paddock.txt
```
（中身: deeplabcut[modelzoo], opencv-python, scipy, pandas, numpy, tables, yt-dlp, pytesseract）

### 2. システムに ffmpeg と tesseract を入れる
- **Windows**: [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) と [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) をインストールしPATHを通す
- **Mac**: `brew install ffmpeg tesseract`
- **Linux**: `sudo apt install ffmpeg tesseract-ocr`

### 3. 動作確認（依存なしでロジックだけ検証）
```bash
python paddock_gait.py --selftest
python paddock_segment.py --selftest
python paddock_compare.py --selftest
python skeleton_overlay.py --selftest
```

> 初回の本番解析時に SuperAnimal のモデル重みが自動ダウンロードされます（要ネット接続）。

---

## 使い方（実戦）

### A. 動画ファイルから（推奨・確実）
パドック周回を録画した動画を用意して:
```bash
python run_paddock.py race.mp4
```
軽く速く回すなら:
```bash
python run_paddock.py race.mp4 --fast --fps 12
```

### B. 動画URLから（自宅PCのみ・YouTube等）
`paddock_gait.py` はURL入力に対応（yt-dlp）:
```bash
python paddock_gait.py "https://www.youtube.com/watch?v=..." --start 1:08 --end 1:18 --no-adapt
```
※データセンター/一部環境ではYouTube側にbot判定されDLできないことがあります（自宅の通常回線推奨）。

### 競馬場ごとのテロップ位置調整
馬番ボックスの座標は競馬場・配信で違います。既定は高知けいばナイター(1920x1140)。
ずれる場合は `--roi x,y,w,h` で指定:
```bash
python run_paddock.py race.mp4 --roi 258,806,120,70
```

---

## 出力
`<動画名>_paddock/` に生成されます:
- **`kehai.html`** … 全頭の気配スコアランキング（ブラウザで開く）
- `*_skeleton.mp4` … 各馬の骨格確認動画（背骨=緑、重心=赤）
- `*_gait_metrics.csv` … 各馬の歩様数値
- `race_umaXX.mp4` … 各馬の切り出しクリップ

---

## 速度の目安（重要）
推論はGPUの有無で大きく変わります:
| 環境 | 1頭あたり | 用途 |
|---|---|---|
| **NVIDIA GPU (CUDA, VRAM 6GB+)** | 数秒〜十数秒 | レース前も狙える |
| **CPUのみ** | 数分 | レース**後**の振り返り向き |

CPUで少しでも速く: `--fast --fps 12` ＋ 真横・単独・短い区間。
GPUが無い場合は、クラウドGPU（Google Colab Pro等）に動画を持ち込む手もあります。

---

## 精度を出すコツ
- **本命馬が「手前・単独・真横」**で写る区間が最も正確（複数馬・斜め・夜間は精度低下）。
- 骨格確認動画で関節点が正しく乗っているか**必ず目視**してから数値を信頼する。
- 気配スコアは**相対比較の目安**であり勝敗の断定ではありません。実結果と突き合わせて重みを育ててください。

---

## 注意
- SuperAnimal-Quadruped モデルは研究用途（非商用）ライセンス。内部検討に留めること。
- 動画URLのダウンロードは各サイトの利用規約・著作権を確認のこと。
