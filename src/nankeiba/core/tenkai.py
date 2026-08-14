"""展開指数 ── 「位置が要るコース」と「前に行ける馬」を別々に数値化して掛ける。

⚠️⚠️ **これは「ズブさ」の指数ではない。**「ズブい馬を走らせるのが南関」という
   話を、こちらが**位置取りの話だと読み違えて**作ったもの。ユーザーの意図は
   「ズブい馬は距離・騎手・競馬場を**変えないと点火しない**」という**変化**の話で、
   位置は結果であって原因ではなかった。そちらは `shigeki.py`。

   このモジュールが測っているのは **コースがどれだけ位置で決まるか** だけ。
   それ自体は事実として有用（下の実測）なので残してあるが、
   **ズブさの指標として使わないこと。**

⚠️⚠️ **その見立ては南関全体では成り立たない。浦和だけの性質だった。**
   4角順位と着順の相関を場×距離帯で測った実測（7,746レース・86,483頭）:

       浦和  短 +0.875 ／ 中 +0.804 ／ 長 +0.866    ← 位置がすべて
       川崎  短 +0.686 ／ 中 +0.643 ／ 長 +0.262
       船橋  短 +0.476 ／ 中 +0.524 ／ 長 +0.484
       大井  短 +0.463 ／ 中 +0.539 ／ 長 +0.528

   南関全体では **上がり順位のほうが効く**（r=+0.723 対 4角の +0.592）。
   上がり最速馬は **45.8%が1着・74.1%が3着内**。
   「南関は前に行った者勝ち」を全場に当てはめないこと。

そこで2つに分けて持つ。**掛けて初めて意味が出る**。

    位置依存度（コース）… そのコースで4角の位置がどれだけ着順を決めるか。
                          0〜1。1に近いほど「前を取れないと話にならない」。
    先行力（馬）        … その馬が4角でふだんどのあたりに居るか。
                          0〜1。1に近いほど前。頭数で正規化してある。

    展開適合度 = 位置依存度 × (先行力 − 0.5) × 2

    プラスなら「位置が要るコースで、前に行ける馬」。
    マイナスなら「位置が要るコースなのに、後ろからしか行けない馬」。
    位置依存度が低いコースでは、先行力が高くても低くても0に近づく（効かない）。

⚠️ **これは能力指数ではない。**BT値（時計）と足し引きしないこと。
   BT値が「どれだけ速く走ったか」なのに対し、これは「その形が今回のコースで
   通用するか」。別の軸なので、並べて見るもので、合成する根拠はまだ無い。

⚠️ **BT値はこの歪みを含んでいる。**BT値は時計しか見ないので、位置依存度の
   高いコース（浦和）では「展開で得をした馬」を高く評価してしまう。
   浦和のBT値を大井のBT値と並べるときは、この指数を横に置くこと。

⚠️ 先行力は**過去走から作る**ので、発走前に使える。実測で、直近6走から作った
   先行力は**次走の実際の4角位置を r=+0.509 で当てる**（n=61,922）。
   1.0にならないのは当然で、枠順・同型の数・当日の馬場で位置は動く。
   ただし「今回このメンバーで前に行けるか」までは分からない。あくまで素材。
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean, median

#: 距離帯の切り方。短距離ほど位置が要る、とは限らない（浦和以外では距離で動く）。
def band(distance: int | None) -> str:
    """'短' / '中' / '長'。"""
    if not distance:
        return "中"
    if distance <= 1300:
        return "短"
    return "中" if distance <= 1600 else "長"


def _corr(a, b) -> float:
    if len(a) < 3:
        return 0.0
    ma, mb = mean(a), mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else 0.0


@dataclass
class PositionWeight:
    """場×距離帯ごとの位置依存度。"""

    dep: dict = field(default_factory=dict)
    n: dict = field(default_factory=dict)

    @classmethod
    def build(cls, rows, *, min_field: int = 6, min_runs: int = 500
              ) -> "PositionWeight":
        """1頭1行のレコード列から作る。

        4角順位と着順を**どちらも頭数で割って**から相関を取る。割らないと
        頭数の多いレースほど数字が大きくなり、頭数の分布の差が混ざる。
        """
        g: dict = defaultdict(lambda: ([], []))
        by: dict = defaultdict(list)
        for r in rows:
            by[r["rid"]].append(r)
        for L in by.values():
            ok = [x for x in L if x.get("corner4") and x.get("finish")]
            if len(ok) < min_field:
                continue
            n = len(ok)
            k = (ok[0]["place"], band(ok[0]["distance"]))
            for x in ok:
                g[k][0].append(x["corner4"] / n)
                g[k][1].append(x["finish"] / n)
        self = cls()
        for k, (p, f) in g.items():
            if len(p) < min_runs:
                continue
            self.dep[k] = round(max(0.0, _corr(p, f)), 3)
            self.n[k] = len(p)
        return self

    def of(self, place: str, distance: int | None) -> float:
        """位置依存度。無ければ同じ場の平均、それも無ければ全体の平均。"""
        k = (place, band(distance))
        if k in self.dep:
            return self.dep[k]
        same = [v for kk, v in self.dep.items() if kk[0] == place]
        if same:
            return round(mean(same), 3)
        return round(mean(self.dep.values()), 3) if self.dep else 0.5

    def dump(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"dep": {"|".join(k): v for k, v in self.dep.items()},
                       "n": {"|".join(k): v for k, v in self.n.items()}},
                      f, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "PositionWeight":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        un = {tuple(k.split("|")): v for k, v in raw["dep"].items()}
        return cls(dep=un, n={tuple(k.split("|")): v for k, v in raw["n"].items()})


def senkou(runs, *, limit: int = 6) -> float | None:
    """その馬の**先行力**。1に近いほど前。頭数で正規化した4角位置の中央値の裏返し。

    `runs` は過去走（新しい順）。`corner_pos` と `field_size` を持つもの。
    ⚠️ **直近に絞ること**（既定6走）。脚質は変わる。全キャリアで平均すると、
       乗り替わりや距離替わりで前に行くようになった馬を拾えない。
    """
    v = []
    for r in runs[:limit]:
        pos = getattr(r, "corner_pos", None) or (r.get("corner_pos") if isinstance(r, dict) else None)
        fld = getattr(r, "field_size", None) or (r.get("field_size") if isinstance(r, dict) else None)
        if pos and fld:
            v.append(pos[-1] / fld)
    return round(1.0 - median(v), 3) if v else None


def fit(place: str, distance: int | None, senkou_val: float | None,
        pw: PositionWeight) -> float | None:
    """展開適合度。プラスなら「位置が要るコースで前に行ける馬」。

    位置依存度が低いコースでは0に近づく（先行力が高くても効かない）。
    """
    if senkou_val is None:
        return None
    return round(pw.of(place, distance) * (senkou_val - 0.5) * 2, 3)


def label(v: float | None, dep: float | None = None) -> str:
    """展開適合度をひとことに。`dep` を渡すと0付近の理由を分けて書ける。

    ⚠️ 0付近には**別の理由が2つ**ある。「コースが位置を要求しない」のと
       「馬が中庸で前にも後ろにも居ない」。混ぜて書くと読み違える。
    """
    if v is None:
        return "―"
    if v >= 0.30:
        return "展開が向く（位置が要る場で前に行ける）"
    if v >= 0.10:
        return "やや向く"
    if v <= -0.30:
        return "**展開が向かない**（位置が要る場で後方から）"
    if v <= -0.10:
        return "やや向かない"
    if dep is not None and dep >= 0.65:
        return "中庸（位置は要る場だが、前でも後ろでもない）"
    return "位置が効きにくい場"
