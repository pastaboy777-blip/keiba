"""点火指数 ── **穴馬が走るタイミング**を測る。

ユーザー指定（2026-08-14）:
    「ズブイ馬を走らせるためには距離や騎手や競馬場を変えないといけないわけよ。
      それでエンジンをあたためて、発射して馬券になる」
    「そのタイミングを指数化したいのよ」「穴馬が走るタイミングを」

⚠️ **「ズブい馬」は静的なタイプではない。**最初これを脚質（後方からしか行けない）
   と読み違えて位置取りの指数を作った（`tenkai.py`）。的外れだった。
   ズブい＝**変化を与えないと点火しない**という意味で、鍵は変化とその順序。

考え方は3段。**変化した当日ではなく、その次が本番**というのが要点。

    ① 変化   … 距離・騎手・競馬場・間隔が前走から変わったか
    ② 予熱   … その変化で**前走に兆候が出ていたか**（着順に出ていなくてよい）
    ③ 点火   … ①と②が揃っていて、まだ人気になっていない

    点火指数 = 変化スコア ＋ 予熱スコア

「変化があったから買う」ではない。変化があって**前走で動けていた**馬を、
まだ人気にならないうちに買う、という形。

⚠️⚠️ **この指数はまだ検証していない。**恒久ルール5（過去開催をまとめた
   勝率・回収率の集計をやらない）に真正面からぶつかるため、意図的に
   測っていない。重みは**根拠のない初期値**であって、実測値ではない。
   使うなら**目の前の開催で**、当たり外れを正直に記録すること。

⚠️ 予熱の兆候は**その馬自身の過去と比べる**。他馬と比べると、単に強い馬が
   上位に来るだけで「上向き」を拾えない。

⚠️ 「まだ人気になっていない」は指数に入れていない。オッズは発走直前まで
   動くし、指数に混ぜると「人気薄だから買い」という同義反復になる。
   人気は**外で掛ける**こと。

── 目の前の1開催で回した結果（2026-08-14 大井・10R・116頭）──────────

⚠️⚠️ **全馬では効いたが、肝心の穴では逆になった。**

    全馬        6.0点以上 34.8% ／ 4.5〜6.0 26.9%
                3.0〜4.5 23.5% ／ 3.0未満 21.2%     （きれいに単調）

    6人気以下   **点火** 15頭 → 3着内 **0頭**
                予熱中   18頭 → 3着内  3頭（16.7%）
                変化のみ 11頭 → 3着内  0頭
                材料なし 12頭 → 3着内  2頭（16.7%）

   実際に来た穴6頭のうち指数が高かったのは1頭だけ（1R フカガワブギョー
   6.0点・8人気3着）。9人気2着と8人気2着は**2.0点「材料なし」**だった。
   **人気馬が来ることは当てて、穴が来ることは当てていない。狙いと逆。**

   1日116頭なので「効かない」と決めるには早い（点火の穴が15頭では0本でも
   珍しくない）。ただし**構造を疑うべき兆候**として記録する。

   思い当たる理由: **変化はオッズに織り込まれている。**乗り替わりも距離替わりも
   他場替わりも出馬表を見れば誰でも分かるので、変化の大きい馬は既に買われて
   いる。人気薄で残るのは「変化はあるが買われない理由がある」馬になる。

   直すなら重みではなく構造。有力なのは**予熱を「着順に出ていないもの」に
   絞る**こと。いまは `W_FINISH`（着順が上がった）を加点しているが、着順は
   人気に反映される。**着順は悪いのに上がり・位置だけ良化した**馬に絞るほうが
   「エンジンは温まったがまだ結果に出ていない」という趣旨に合う。未着手。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

#: 変化の重み[点]。⚠️ **未測定の初期値。**
W_PLACE = 2.0          # 競馬場が替わった
W_JOCKEY = 1.5         # 乗り替わり
W_DIST = 1.5           # 距離が変わった（400m以上でさらに加点）
W_DIST_BIG = 1.0
W_REST = 1.5           # 間隔が空いた（休み明け）
W_TIGHT = 1.0          # 詰めて使ってきた

#: 予熱の重み[点]。⚠️ **未測定の初期値。**
W_AGARI = 2.0          # 前走の上がりが自己ベースより速かった
W_POS = 1.5            # 前走で位置を上げた
W_FINISH = 1.0         # 前走で着順が上がった
W_CHAINED = 1.5        # 前走**も**変化だった（予熱が済んでいる）

#: 休み明けとみなす日数 / 詰めて使ったとみなす日数。
REST_DAYS = 60
TIGHT_DAYS = 14


def _days(a: str, b: str) -> int | None:
    """'2026-08-10' と '2026-07-14' の日数差。"""
    import datetime as dt
    try:
        return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days
    except (ValueError, AttributeError):
        return None


def _get(r, k):
    return getattr(r, k, None) if not isinstance(r, dict) else r.get(k)


@dataclass
class Ignition:
    """1頭ぶんの点火判定。"""

    score: float = 0.0
    change: float = 0.0
    preheat: float = 0.0
    tags: list = field(default_factory=list)
    warm: list = field(default_factory=list)

    def label(self) -> str:
        """状態をひとことに。

        ⚠️ **「変化なし」と「兆候なし」を混ぜないこと。**変化が無くても前走で
           大きく動いていれば、それは「前走で発射済み」であって材料が無いのとは
           別の状態。実際そこを混ぜて、前走1着で上がりも位置も良化していた馬を
           「点火の材料が無い」と表示するバグを出した。
           なお前走で発射済みの馬は**もう人気になっている**ことが多いので、
           穴として狙う対象ではない。区別できないと、そこを取り違える。
        """
        fired = self.preheat >= 3.0
        if self.change >= 1.5:
            if fired:
                return "**点火**（変化があり、前走で動けていた）"
            if self.preheat >= 1.5:
                return "予熱中（変化はあるが兆候は弱い）"
            return "変化のみ（前走に兆候なし）"
        if fired:
            return "前走で発射済み（今回は変化なし・人気になりやすい）"
        return "材料なし"


def changes(place: str, distance: int | None, jockey: str | None,
            date: str, prev) -> tuple[float, list]:
    """今回の変化を点数と札にする。前走が無ければ (0, [])。"""
    if prev is None:
        return 0.0, []
    s, tags = 0.0, []
    p_place, p_dist = _get(prev, "place"), _get(prev, "distance")
    p_jk, p_date = _get(prev, "jockey"), _get(prev, "date")
    if p_place and place and p_place != place:
        s += W_PLACE
        tags.append(f"{p_place}→{place}")
    if p_jk and jockey and p_jk != jockey:
        s += W_JOCKEY
        tags.append(f"乗替({p_jk}→{jockey})")
    if p_dist and distance and p_dist != distance:
        s += W_DIST
        d = abs(p_dist - distance)
        if d >= 400:
            s += W_DIST_BIG
        tags.append(f"{'短縮' if p_dist > distance else '延長'}{d}m")
    gap = _days(date, p_date) if p_date else None
    if gap is not None:
        if gap >= REST_DAYS:
            s += W_REST
            tags.append(f"**{gap}日ぶり**")
        elif gap <= TIGHT_DAYS:
            s += W_TIGHT
            tags.append(f"中{gap}日")
    return s, tags


def preheat(runs) -> tuple[float, list]:
    """**前走に兆候が出ていたか**。`runs` は過去走（新しい順）。

    着順に出ていなくてよい。むしろ着順に出ていないほうが人気にならない。

    ⚠️ すべて**その馬自身の過去**と比べる。他馬との比較では「強い馬」しか
       拾えず、「上向いた馬」を拾えない。
    """
    if not runs or len(runs) < 2:
        return 0.0, []
    last, rest = runs[0], runs[1:]
    s, warm = 0.0, []

    ags = [a for a in (_get(r, "last3f_sec") for r in rest) if a]
    la = _get(last, "last3f_sec")
    if la and len(ags) >= 2 and la < median(ags) - 0.2:
        s += W_AGARI
        warm.append(f"上がり{la}（自己{median(ags):.1f}より速い）")

    def relpos(r):
        p, f = _get(r, "corner_pos"), _get(r, "field_size")
        return (p[-1] / f) if (p and f) else None

    ps = [x for x in (relpos(r) for r in rest) if x is not None]
    lp = relpos(last)
    if lp is not None and len(ps) >= 2 and lp < median(ps) - 0.10:
        s += W_POS
        warm.append("前走で位置を上げた")

    lf, pf = _get(last, "finish_pos"), _get(rest[0], "finish_pos")
    if lf and pf and lf < pf:
        s += W_FINISH
        warm.append(f"着順が上がった（{pf}着→{lf}着）")

    c, _ = changes(_get(last, "place"), _get(last, "distance"),
                   _get(last, "jockey"), _get(last, "date") or "", rest[0])
    if c >= 3.0:
        s += W_CHAINED
        warm.append("前走も変化だった（予熱済み）")
    return s, warm


def ignition(place: str, distance: int | None, jockey: str | None,
             date: str, runs) -> Ignition:
    """今回の出走について点火指数を出す。`runs` は過去走（新しい順）。"""
    if not runs:
        return Ignition()
    c, tags = changes(place, distance, jockey, date, runs[0])
    p, warm = preheat(runs)
    return Ignition(score=round(c + p, 1), change=round(c, 1),
                    preheat=round(p, 1), tags=tags, warm=warm)
