"""対戦（H2H）ネットワークの構築 — 結果ページを主データにする。

⚠️ 実装上の重要な教訓（2026-07-26 に実データで発覚したバグ）:
  当初は**出馬表の馬柱だけ**から対戦関係を作っていた。楽天の馬柱は直近数走しか
  載らないため、古い対戦が丸ごと欠落する。実例:

    2026-04-22 園田10R(820m) で ミスターエヌ(1着) が ベラジオアブロード(2着) に先着。
    3ヶ月後の 2026-07-23 園田9R で、1.8倍の断然人気だったベラジオアブロードが4着に
    敗れ、ミスターエヌ(9人気)が勝って三連単1,239万円。
    → だが ベラジオアブロードの馬柱は 6/11・5/20 の2走分しか無く、**4/22の対戦が
      見えなかった**ため、アラートが鳴らなかった。

  **結果ページ(race_performance)には、その日の全出走馬と着順が載っている。**
  こちらを主データにすれば対戦が漏れない。馬柱は補助（未キャッシュのレースを埋める）。

  修正の効果（南関 102,420ペア）:
    対戦歴あり率 27.7% → **30.2%**（人気差6以上）、人気差3-5では発火率が約2倍(7.1%)。
    効果量は据え置き（+11.3pt）だが、**アラートが鳴る機会が増えた**。

依存ライブラリなし。
"""

from __future__ import annotations

import glob
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field

from ..scraping import rakuten as rk

CACHE = "data/cache/rakuten"

# レース指紋: (日付, 場, 距離, 頭数)
RaceKey = tuple


@dataclass
class H2HNet:
    """馬名 → {レース指紋: 着順} の対戦ネットワーク。"""

    finish_of: dict[str, dict[RaceKey, int]] = field(default_factory=lambda: defaultdict(dict))
    races_of: dict[str, set] = field(default_factory=lambda: defaultdict(set))
    n_result: int = 0        # 結果ページ由来の走破記録数
    n_history: int = 0       # 馬柱由来の走破記録数

    # ------------------------------------------------------------------
    def add(self, horse: str, key: RaceKey, finish: int, *, from_result: bool) -> None:
        if key in self.finish_of[horse]:
            return
        self.finish_of[horse][key] = finish
        self.races_of[horse].add(key)
        if from_result:
            self.n_result += 1
        else:
            self.n_history += 1

    def record(self, a: str, b: str, before: str | None = None) -> tuple[int, int]:
        """(aの先着回数, bの先着回数)。before を渡すとその日より前だけ（リーク防止）。"""
        aw = bw = 0
        for k in self.races_of[a] & self.races_of[b]:
            if before is not None and k[0] >= before:
                continue
            fa, fb = self.finish_of[a].get(k), self.finish_of[b].get(k)
            if fa is None or fb is None or fa == fb:
                continue
            if fa < fb:
                aw += 1
            else:
                bw += 1
        return aw, bw

    def common_races(self, a: str, b: str) -> list[RaceKey]:
        return sorted(self.races_of[a] & self.races_of[b])


def build(cache_dir: str | os.PathLike = CACHE, *, use_history: bool = True) -> H2HNet:
    """キャッシュから対戦ネットワークを構築する。

    結果ページ（全出走馬が載る）を主データに、馬柱を補助に使う。
    """
    net = H2HNet()
    cache_dir = str(cache_dir)

    # --- 主: 結果ページ ---
    for pf in sorted(glob.glob(os.path.join(cache_dir, "race_performance_list_RACEID_*.html"))):
        m = re.search(r"RACEID_(\d+)", pf)
        if not m:
            continue
        rid = m.group(1)
        cf = os.path.join(cache_dir, f"race_card_list_RACEID_{rid}.html")
        if not os.path.exists(cf):
            continue
        try:
            hd = rk.parse_card(open(cf, encoding="utf-8").read())["header"]
            res = rk.parse_result(open(pf, encoding="utf-8").read())
        except Exception:                        # noqa: BLE001
            continue
        place, dist = hd.get("place"), hd.get("distance")
        if not place or not dist or not res:
            continue
        key = (f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}", place, dist, len(res))
        for r in res:
            if r.get("name"):
                net.add(r["name"], key, r["finish"], from_result=True)

    # --- 補助: 馬柱（未キャッシュのレースを埋める） ---
    if use_history:
        for cf in sorted(glob.glob(os.path.join(cache_dir, "race_card_list_RACEID_*.html"))):
            try:
                card = rk.parse_card(open(cf, encoding="utf-8").read())
            except Exception:                    # noqa: BLE001
                continue
            for e in card["entries"]:
                for r in e["history"]:
                    if not (r.date and r.place and r.distance and r.field_size and r.finish_pos):
                        continue
                    net.add(e["name"], (r.date, r.place, r.distance, r.field_size),
                            r.finish_pos, from_result=False)
    return net


@dataclass
class Standing:
    """今日の面子に対する序列の内訳。

    ⚠️ 「11勝3敗」のような通算だけでは判断を誤る。同じ勝ち越しでも
    **完封して積んだ勝ち**と**まだ争っている相手から拾った勝ち**は意味が違う。
    実測（人気薄）: 3頭以上を完封 lift1.91 / 3頭以上に完封され lift0.41 に対し、
    2勝1敗のような未決着ペアは効果が薄い。→ 必ず分けて見る。
    """

    horse: str
    umaban: int | None
    swept: list[tuple[str, int]] = field(default_factory=list)      # 完封した相手 [(名, 勝)]
    swept_by: list[tuple[str, int]] = field(default_factory=list)   # 完封された相手 [(名, 敗)]
    contested: list[tuple[str, int, int]] = field(default_factory=list)  # 争い中 [(名, 勝, 敗)]

    @property
    def wins(self) -> int:
        return (sum(w for _, w in self.swept)
                + sum(w for _, w, _ in self.contested))

    @property
    def losses(self) -> int:
        return (sum(l for _, l in self.swept_by)
                + sum(l for _, _, l in self.contested))

    def summary(self) -> str:
        parts = [f"{self.wins}勝{self.losses}敗"]
        if self.swept:
            parts.append("完封" + "・".join(f"{n}({w}-0)" for n, w in self.swept))
        if self.swept_by:
            parts.append("被完封" + "・".join(f"{n}(0-{l})" for n, l in self.swept_by))
        if self.contested:
            parts.append("争い中" + "・".join(f"{n}({w}-{l})" for n, w, l in self.contested))
        return " / ".join(parts)


def standings(net: "H2HNet", entries: list[dict], *,
              before: str | None = None, min_meets: int = 2) -> list[Standing]:
    """今日の面子について、完封／被完封／争い中を分けて集計する。

    min_meets 未満の対戦（1戦だけ等）は「完封」とみなさず争い中に入れる
    ＝ 1回勝っただけで序列が決まったとは言わない。
    """
    out: list[Standing] = []
    for me in entries:
        st = Standing(horse=me["name"], umaban=me.get("umaban"))
        for other in entries:
            if other is me:
                continue
            w, l = net.record(me["name"], other["name"], before)
            if w + l == 0:
                continue
            if w + l >= min_meets and l == 0:
                st.swept.append((other["name"], w))
            elif w + l >= min_meets and w == 0:
                st.swept_by.append((other["name"], l))
            else:
                st.contested.append((other["name"], w, l))
        out.append(st)
    out.sort(key=lambda s: (-len(s.swept), -(s.wins - s.losses), len(s.swept_by)))
    return out


@dataclass
class Alert:
    """人気薄が人気馬に過去先着している＝その人気馬を疑う材料。"""

    ana: str
    ana_umaban: int | None
    ana_ninki: int
    fav: str
    fav_umaban: int | None
    fav_ninki: int
    gap: int
    win: int
    loss: int

    @property
    def note(self) -> str:
        return (f"{self.ana_ninki}人気{self.ana} が {self.fav_ninki}人気{self.fav} に"
                f"過去{self.win}-{self.loss}で先着")


def alerts(net: H2HNet, entries: list[dict], *, before: str | None = None,
           min_gap: int = 3) -> list[Alert]:
    """entries=[{name, umaban, ninki}] → 発火したアラート一覧。

    実測（南関102,420ペア・7月ホールドアウト）:
      人気差6以上 … 対戦歴なし17.0% → 過去に先着28.3%（+11.3pt / HO +13.7pt）
      人気差3-5  … 対戦歴なし29.5% → 過去に先着38.3%（+8.9pt / HO +7.7pt）
      ※「過去に敗退」は -0.2pt でほぼ無効。**先着歴だけが効く**（非対称）。
      予測するのは「勝つこと」ではなく「**あの馬より上に来ること**」。
    """
    out: list[Alert] = []
    for lo in entries:
        for hi in entries:
            if lo is hi or not lo.get("ninki") or not hi.get("ninki"):
                continue
            gap = lo["ninki"] - hi["ninki"]
            if gap < min_gap:
                continue
            w, l = net.record(lo["name"], hi["name"], before)
            if w > l:
                out.append(Alert(ana=lo["name"], ana_umaban=lo.get("umaban"),
                                 ana_ninki=lo["ninki"], fav=hi["name"],
                                 fav_umaban=hi.get("umaban"), fav_ninki=hi["ninki"],
                                 gap=gap, win=w, loss=l))
    out.sort(key=lambda a: (-a.gap, a.ana_ninki))
    return out
