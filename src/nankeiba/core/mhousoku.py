"""Mの法則（今井雅宏）の考え方を、南関のデータで使える形にしたもの。

⚠️ **これは今井雅宏氏の理論そのものではない。**公開されている用語集・解説から
   読み取った概念を、こちらが独自に南関のデータへ落とし込んだ実装。
   原典（書籍）は参照していないので、**本家と一致しない**。
   本家の指数を名乗らないこと。

── 理論の骨格（公開情報から）────────────────────────────────

**M = Mind（精神）／ Minus（消耗）／ Mannerism（慣れと繰り返し）。**

    サラブレッドは人為的に管理され、**病的なストレスを常に抱えて走っている**。
    ストレスが強いと凡走する。ストレスを破って心身が新鮮になったとき走る。

理論は3次元で構成される。

    横軸   … メンバー間のストレスと、その中での異端性
    時間軸 … 競走馬のリズムと**ショック療法**
    中心点 … 馬の構造分析（M3タイプ）

**M3タイプ**は S（闘争心）／ C（集中力）／ L（鈍感）。主構造＋（副構造）で
`LC(S)` のように書く。3つがまとまっている万能型を M系 と呼ぶ。

**ショック療法** … 馬を活性化させ「苦から楽へ」の思いをさせて激走させる手法。
   **有効なショックが多いほど激走の可能性が上がる。**
   代表例: 距離変更ショック（延長／短縮）、位置取りショック（前走先行→今回差し、
   またはその逆）、内枠ショック、休み明け、格上げ、メンバー替わり。

**鮮度（フレッシュ）** … 休み明け・条件替わり・メンバー替わり・格上げ戦・
   位置取りショックで**上がる**。

**硬直** … 心身構造が硬くなること。冬に起きやすい。そして決定的に重要なのは、
   **「休み明けの激走」「苦手な距離での無理な走り」「強引なショックでの激走」の
   "後" に起こる**という点。つまり**激走の直後は反動が来る**。

⚠️⚠️ **この「硬直」こそが、こちらが自力で作った点火指数に完全に欠けていた要素。**
   `shigeki.py` は「変化があって前走で動けた馬を買う」までしか作れておらず、
   **激走の後に消す**という半分が無かった。8/14 大井で「点火」と判定した人気薄
   15頭が1頭も来なかったのは、そこに反動待ちの馬が混ざっていたからかもしれない
   （未検証）。米国の Ragozin が言う「バウンス」と同じ構造だが、
   **発動条件がより具体的**（休み明け／苦手距離／強引なショック の後）。

⚠️ **「コース替わり」は競馬場替わりではない。**Mの法則では**道中の位置取りを
   変える**こと（前走先行→今回差し、またはその逆）を指す。こちらは最初これを
   「競馬場が替わる」と読み違えて実装していた（`shigeki.py`）。

⚠️ **未検証。**重みはすべて根拠のない初期値。恒久ルール5により過去開催の
   一括集計はしていない。使うなら目の前の開催で正直に記録すること。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from statistics import median

#: ショックの重み[点]。⚠️ 未測定の初期値。
W_DIST = 1.0           # 距離変更ショック（延長／短縮）
W_DIST_BIG = 0.5       # 400m以上の変更
W_POS = 1.5            # 位置取りショック（前走と道中の位置が変わる見込み）
W_INNER = 1.0          # 内枠ショック
W_REST = 1.5           # 休み明け
W_CLASSUP = 1.0        # 格上げ
W_PLACE = 1.0          # 場替わり（メンバーが総入れ替えになる）
W_JOCKEY = 0.8         # 乗り替わり

#: 硬直（反動）の重み[点]。**マイナス方向**に効く。
K_AFTER_REST = 2.0     # 休み明けで激走した直後
K_ODD_DIST = 1.5       # 苦手な距離で激走した直後
K_MULTI = 1.5          # 多重ショックで激走した直後
K_PEAK = 1.0           # 単純に前走が激走だった

#: 休み明けとみなす日数。
REST_DAYS = 60
#: 「激走」＝この人気以下で3着内。
GEKISO_POP = 5
#: 内枠とみなす割合（頭数に対する枠の位置）。
INNER_FRAC = 0.35


def _days(a: str, b: str) -> int | None:
    try:
        return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days
    except (ValueError, AttributeError, TypeError):
        return None


def _g(r, k):
    return getattr(r, k, None) if not isinstance(r, dict) else r.get(k)


def is_gekiso(run) -> bool:
    """**激走**か。人気を大きく裏切って好走した走り。

    ⚠️ 「1着だった」ではない。1番人気の1着は激走ではない（消耗が違う）。
       人気薄で3着内に来た走りだけを激走とみなす。**その直後に硬直が来る。**
    """
    f, p = _g(run, "finish_pos"), _g(run, "popularity")
    return bool(f and p and f <= 3 and p >= GEKISO_POP)


def leg(run) -> float | None:
    """その走の道中の位置（0=最前、1=最後方）。頭数で正規化。"""
    pos, fld = _g(run, "corner_pos"), _g(run, "field_size")
    if not pos or not fld:
        return None
    return pos[-1] / fld


@dataclass
class MState:
    """1頭ぶんの「鮮度」と「硬直」。"""

    fresh: float = 0.0            # 鮮度（ショックの合計）
    stiff: float = 0.0            # 硬直リスク（反動）
    shocks: list = field(default_factory=list)
    risks: list = field(default_factory=list)

    @property
    def score(self) -> float:
        """鮮度から硬直を引いたもの。**プラスが買い、マイナスが消し。**"""
        return round(self.fresh - self.stiff, 1)

    def label(self) -> str:
        if self.stiff >= 2.0:
            return "**硬直**（前走の反動が来る）"
        if self.fresh >= 3.5:
            return "**鮮度が高い**（ショックが複数）"
        if self.fresh >= 2.0:
            return "やや新鮮"
        return "変わり映えしない"


def shocks(place: str, distance: int | None, jockey: str | None,
           gate: int | None, field_size: int | None, race_class: str | None,
           date: str, runs) -> tuple[float, list]:
    """今回の出走に掛かっている**ショック**を数える。

    「有効なショックが多いほど激走の可能性が上がる」という考え方に沿って、
    足し合わせるだけにしてある。**掛けない**（1つでも欠けると0になるのは違う）。
    """
    if not runs:
        return 0.0, []
    prev = runs[0]
    s, tags = 0.0, []

    p_dist = _g(prev, "distance")
    if p_dist and distance and p_dist != distance:
        s += W_DIST
        d = abs(p_dist - distance)
        if d >= 400:
            s += W_DIST_BIG
        tags.append(f"{'短縮' if p_dist > distance else '延長'}{d}m")

    # 位置取りショック。前走が極端な位置だった馬は、今回動かす余地が大きい。
    # ⚠️ 本当は「今回どこを走るか」が要るが、それは走ってみないと分からない。
    #    ここでは**前走が極端だったこと**を代理にしている。近似であることを消さない。
    lp = leg(prev)
    if lp is not None and (lp <= 0.25 or lp >= 0.75):
        s += W_POS
        tags.append(f"位置取り極端（前走{'前' if lp <= 0.25 else '後'}）")

    if gate and field_size and gate <= max(2, field_size * INNER_FRAC):
        pg = _g(prev, "gate")
        pf = _g(prev, "field_size")
        if pg and pf and pg / pf > INNER_FRAC:
            s += W_INNER
            tags.append(f"内枠ショック（{pg}→{gate}番）")

    gap = _days(date, _g(prev, "date"))
    if gap is not None and gap >= REST_DAYS:
        s += W_REST
        tags.append(f"休み明け{gap}日")

    if _g(prev, "place") and place and _g(prev, "place") != place:
        s += W_PLACE
        tags.append(f"{_g(prev, 'place')}→{place}")

    if _g(prev, "jockey") and jockey and _g(prev, "jockey") != jockey:
        s += W_JOCKEY
        tags.append("乗替")

    return s, tags


def stiffness(runs) -> tuple[float, list]:
    """**硬直**（反動）リスク。前走で無理をした直後か。

    ⚠️ Mの法則で硬直は「休み明けの激走」「苦手な距離での無理な走り」
       「強引なショックでの激走」の**後**に起こるとされる。
       つまり**激走そのものが次走の減点材料**になる。
       買う材料しか持たない指数は、ここで必ず外す。
    """
    if len(runs) < 2:
        return 0.0, []
    last, rest = runs[0], runs[1:]
    if not is_gekiso(last):
        return 0.0, []
    s, risks = K_PEAK, [f"前走が激走（{_g(last, 'popularity')}人気"
                        f"{_g(last, 'finish_pos')}着）"]

    gap = _days(_g(last, "date"), _g(rest[0], "date"))
    if gap is not None and gap >= REST_DAYS:
        s += K_AFTER_REST
        risks.append(f"しかも休み明け（{gap}日）での激走")

    ds = [_g(r, "distance") for r in rest if _g(r, "distance")]
    ld = _g(last, "distance")
    if ld and len(ds) >= 3 and abs(ld - median(ds)) >= 300:
        s += K_ODD_DIST
        risks.append(f"しかも普段と違う距離（{ld}m／普段{median(ds):.0f}m）")

    c, _ = shocks(_g(last, "place"), ld, _g(last, "jockey"), _g(last, "gate"),
                  _g(last, "field_size"), None, _g(last, "date") or "", rest)
    if c >= 3.0:
        s += K_MULTI
        risks.append("しかも多重ショックでの激走")
    return s, risks


def state(place: str, distance: int | None, jockey: str | None,
          gate: int | None, field_size: int | None, race_class: str | None,
          date: str, runs) -> MState:
    """今回の出走について鮮度と硬直を出す。`runs` は過去走（新しい順）。"""
    if not runs:
        return MState()
    f, tags = shocks(place, distance, jockey, gate, field_size,
                     race_class, date, runs)
    k, risks = stiffness(runs)
    return MState(fresh=round(f, 1), stiff=round(k, 1), shocks=tags, risks=risks)
