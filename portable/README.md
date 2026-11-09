# portable ── 他のプロジェクトへ持ち出せるもの

地方競馬の予想ツールを作る過程で出てきた、**題材に依存しない部分**だけを集めた。
ここのファイルは `scripts/ana/` とは独立していて、そのままコピーして使える。

| | 中身 |
|---|---|
| `level.py` | **条件ごとの水準をつくり、同じ対象が両方を経験した記録で系統差を測って補正する。** 拠点・機材・検査室・担当者など、測る場所で数値の水準がずれるデータに使える |
| `checks.md` | **検証の型。**「効く」と言う前に通すチェック |
| `pitfalls.md` | **踏んだ穴の記録。**理由つき。ここがいちばん価値があるかもしれない |
| `chart/` | **図の作り。**縦横に意味を持たせた帯の図のパターン（CSS と描画の型） |

## level.py のいちばん短い使い方

```python
from level import Level

rows = [{"who": "A", "where": "東", "what": "検査1", "val": 12.3}, ...]
L = Level(rows, subject="who", group="where", cond="what", value="val").fit()
print(L.report())
L.adjusted(value=12.3, group="東", cond="検査1")   # 基準の場所に揃えた値
```

`fit()` は2段階で動く。

1. `(group, cond)` ごとの中央値を引く
2. **複数の group を経験した subject** だけを使って、残った系統差を出す

2 が要る理由は `level.py` の冒頭に書いてある。
**1だけでは揃わない。**group ごとに顔ぶれが違うと、中央値自体が引きずられるため。

## 持ち出せないもの

データの取得（特定サイトのスクレイピング）、競馬固有の指標、
`toki.json` / `soto.json` の中身。これらは `scripts/ana/` に置いたまま。

## chart の使い方

```python
from band import render, page
blocks = [render(items, key=lambda d: d["v"], label=lambda d: d["name"],
                 tags=lambda d: ['<span class="sm">上位</span>'] if ... else [],
                 zone=(0, 2, "注目する範囲"),
                 title="例", sub="横＝順序のある量（右が大きい）")]
open("out.html", "w").write(page(blocks, "見出し", "説明"))
```

`python3 band.py out.html` で最小例が出る。
HTML を画像にするなら headless の Chromium に `--screenshot` を渡す。

**守ること**は `band.py` の冒頭に書いてある。とくに
**「縦に意味が無いなら縦に帯を引かない」** と **「強さを色で表さない」** の2つは、
実際にこれで失敗したもの。
