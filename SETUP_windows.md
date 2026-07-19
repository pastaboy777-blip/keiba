# Windows セットアップ手順（run_paddock.py をPCで動かす)

初めてでも進められるよう、順番に書きます。所要40〜60分（ダウンロード時間込み)。
> 目安: このPCはCPU動作なので、1頭の解析に数分かかります。「レース後の分析」向きです。

---

## 手順1. Python を入れる
1. https://www.python.org/downloads/ を開き **Python 3.11** をダウンロード
2. インストーラを起動したら、最初の画面で **「Add python.exe to PATH」に必ずチェック** → Install
3. 確認: スタートメニューで「cmd」と検索して**コマンドプロンプト**を開き、次を入力
   ```
   python --version
   ```
   `Python 3.11.x` と出ればOK

## 手順2. ffmpeg と Tesseract を入れる（Windows 11なら winget が簡単)
コマンドプロンプトで順に実行:
```
winget install Gyan.FFmpeg
winget install UB-Mannheim.TesseractOCR
```
> winget が無い/エラーの場合は下の「winget が使えない場合」を参照。
> インストール後、**コマンドプロンプトを一度閉じて開き直す**（PATH反映のため)。

確認:
```
ffmpeg -version
tesseract --version
```
どちらもバージョンが出ればOK。

## 手順3. ツール一式をダウンロード
1. ブラウザで自分のリポジトリを開く:
   `https://github.com/pastaboy777-blip/keiba`
2. ブランチを **`claude/paddock-gait-setup-cv35gj`** に切り替え
   （「main」と書かれたボタン → ブランチ一覧から選択)
3. 緑の **「Code」ボタン → 「Download ZIP」**
4. ダウンロードしたZIPを**展開**（例: `ドキュメント\keiba` に置く)

## 手順4. 必要なパッケージを入れる
コマンドプロンプトで、展開したフォルダに移動して実行:
```
cd %USERPROFILE%\Documents\keiba
pip install -r requirements-paddock.txt
```
> torch など大きいものを含むので5〜15分かかります。エラーが出たら内容をコピーして相談してください。

## 手順5. 動作確認（依存なしでロジック検証)
```
python paddock_gait.py --selftest
python paddock_segment.py --selftest
python paddock_compare.py --selftest
python skeleton_overlay.py --selftest
```
それぞれ `SELFTEST PASSED` と出ればセットアップ完了！

---

## 使う（実戦)
録画したパドック動画を keiba フォルダに置いて:
```
python run_paddock.py 録画.mp4 --fast --fps 12
```
- 初回だけ、AIモデルの重みが自動ダウンロードされます（ネット接続が必要・数百MB)
- 終わると `録画_paddock\` フォルダができ、中の **`kehai.html`** をダブルクリックすると気配ランキングが見られます
- `_skeleton.mp4` が各馬の骨格確認動画（背骨=緑・重心=赤)

競馬場ごとにテロップ位置がずれる場合は `--roi x,y,w,h` を付けて調整（README_paddock.md 参照)。

---

## winget が使えない場合（手動インストール)
- **ffmpeg**: https://www.gyan.dev/ffmpeg/builds/ の「release full」をDL → 展開 → `bin` フォルダを環境変数PATHに追加
- **Tesseract**: https://github.com/UB-Mannheim/tesseract/wiki のインストーラをDL → インストール（PATHに追加するオプションにチェック)
- PATHの通し方が分からなければ聞いてください。

## うまくいかないときは
- エラーメッセージを**そのままコピー**して送ってください。どこで詰まったか一緒に直します。
- `pip install` で失敗する場合、`pip install --upgrade pip` を先に実行してから再試行。

---

## もっと簡単・速くしたい人へ（Google Colab)
PCへのインストールが大変・遅い場合、**Google Colab**（ブラウザで動く・無料GPUあり)という手もあります。
必要なら Colab 用の手順も用意します（インストール不要で、GPUで数倍速い)。
