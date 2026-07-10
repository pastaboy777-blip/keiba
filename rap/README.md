# 🎤 chill rap kit — "Slow Motion"

チル/リラックス系の lo-fi ヒップホップ・ビートとオリジナル歌詞(日英ミックス)のセット。
**外部ライブラリ不要**(Python 標準ライブラリのみ)。

## 中身

| ファイル | 内容 |
|---|---|
| `beat.py` | lo-fi ビートを生成して WAV を書き出すスクリプト |
| `chill_beat.wav` | 生成済みビート(80 BPM / key C / 約49秒) |
| `lyrics.md` | オリジナル歌詞「Slow Motion」(日英ミックス) |

## 使い方

```bash
# 既定(80 BPM・16小節)で chill_beat.wav を生成
python3 rap/beat.py

# テンポや長さを変える
python3 rap/beat.py --bpm 82 --bars 24 --out my_beat.wav

# シードを変えるとノイズ/揺らぎの表情が変わる
python3 rap/beat.py --seed 42
```

再生は好きなプレイヤーで(例: `afplay` / `ffplay` / ブラウザにドラッグ)。

## ビートの構成

- **コード進行**: `Cmaj7 → Am7 → Dm7 → G7`(I–vi–ii–V、lo-fi 定番)
- **ドラム**: キック(ピッチスイープ)/ スネア / スイングした 8分ハイハット
- **音源**: Rhodes 風コード + まるいサインベース
- **lo-fi 加工**: ソフトクリップ + ビニールのプチノイズ + 薄いヒス

## カスタムしたいとき

`beat.py` の以下をいじると雰囲気が変わる:

- `PROGRESSION` … コード進行(音名で指定)
- `build_beat()` 内のハイハット/キック配置 … リズムのノリ
- `rhodes_chord()` の `detune` … コードの揺れ(大きいほど不安定でエモい)

歌詞は `lyrics.md`。テーマ違い(パーティー系・チルアウト系など)も作れます。
