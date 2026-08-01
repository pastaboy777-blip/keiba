"""中央(JRA)の穴馬抽出 ── 能力側と市場側のズレだけを見る3段構え。

    穴＝弱い馬ではない。「今日の条件なら足りるのに、市場がそれを値段に
      織り込んでいない馬」。だから測るものを2つに分けて、食い違いだけを見る。

        能力側 … オッズを一切見ずに、走破時計だけから作る
        市場側 … 単勝オッズ／人気

    能力側が上位で市場側が下位。両方揃った馬だけが穴になる。
    片方だけなら、ただの本命か、ただの弱い馬。

第1段 時計指数（能力側をオッズなしで作る）
    ① 各馬の過去走から、**そのレースの勝ちタイム**を復元する（RunRecord.win_time_sec）。
    ② 復元勝ちタイムを条件で分解する（最小二乗法）。距離・馬場種・馬場状態・
       クラス・世代・競馬場、そして**ペース記号 H/M/S**。
    ③ 各走を「標準勝ち時計から**その馬自身が**何秒速く走ったか」に換算する
       （＝ レースの速さ − 勝ち馬との着差）。プラスなら標準より速い。

    ⚠️ 当初は「自分の着順は使わない。10着でもレースが速ければ速い」という前提で
       レースの勝ち時計だけを見ていた（`fast()`）。**それだと順位付けの力が
       ほぼ無い。** 2026-08-01 中央27レースの実測:

           指数の作り方            レース内スピアマン  条件1位の勝率/複勝率
           レースの勝ち時計              +0.095      15.0% / 30.0%
           自分の走破タイム              +0.319      25.0% / 60.0%
           着差を半分だけ                +0.222      25.0% / 50.0%
           （参考）単なる人気             +0.504

       速いレースに「出ていた」だけでは足りない。**そこで自分がどれだけの時計で
       走ったか**が要る。着差は着順ではなく**時計の差**なので、
       「オッズを見ない」という原則は保たれている。
       南関のエンジンB（実測 複勝率67%）も自分の走破タイムを使っている。
       JRA版だけがそれを捨てていた。`basis="race"` で旧挙動に戻せる。

第2段 3つの門（すべて通った馬だけ候補）
    ① 条件順が上位          … 今日の条件で足りている（＝ベスト1発）
    ② 実力順が上位**でない** … 地力が目立つ馬は人気を被る（＝ふだんの水準）
    ③ 市場で人気がない      … 値段が付いていない
    ①だけ通ると本命サイド、③だけ通るとただの人気薄。①と③が同時に立つことが
    穴の条件で、②はそれを機械的に担保するための門。

    ⚠️ 実力指数を「全走のベスト」で定義してはいけない。条件指数は「今日の条件での
       ベスト」なので、出走馬の過去走が今日と同じ馬場種ばかりだと **両者が同じ値に
       なり、②が①の焼き直しになる**。実際 2026-08-01 新潟（芝1000mばかり）では
       11Rの上位7頭が条1実1・条2実2…と完全一致し、①②を合わせると
       「条件順ちょうど4位の馬だけ通る」という無意味な門に退化した。
       よって実力指数は **全走の中央値（ふだんの水準）** で定義する。
       ①=一発のピーク / ②=平常運転、と別々のものを測ってはじめて門になる。
       市場は「ふだん強い馬」を買う。ピークだけ高い馬は買われ残る。

第3段 スコア
    score = 条件指数 + w_ana×(人気薄での好走回数) + w_pop×(市場人気)
    第2項が「一発ではなく再現性があるか」、第3項が「どれだけ無視されているか」。

⚠️ この式の弱いところ（承知の上で使う）
  * w_ana=0.5 / w_pop=0.06 は手で置いた値で、回収率で最適化していない。
    → `sensitivity()` で重みを振って◎が入れ替わるかを毎回見ること。
      入れ替わらないなら、手置きであることは結論に影響しない。
  * 時計指数はレース質を完全には分離できない。残差SDを必ず表示し、
    **残差SDより小さい条件指数の差は差と見ない**。
  * クラスをまたいだ絶対比較には使えない。レース内の順位付け専用。

依存ライブラリなし（標準ライブラリのみ）。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from statistics import mean, median

from .interval import RunRecord

#: クラス表記 → 序列（新馬0 …… Ｇ１7）。古い賞金クラス表記も拾う。
_CLASS_ORD = (
    (("新馬", "未勝利", "未出走"), 0),
    (("１勝", "1勝", "500万"), 1),
    (("２勝", "2勝", "1000万", "９００万", "900万"), 2),
    (("３勝", "3勝", "1600万", "1500万"), 3),
    (("ＯＰ", "OP", "オープン", "リステッド", "Ｌ"), 4),
    (("Ｇ３", "G3", "GIII", "ＧIII"), 5),
    (("Ｇ２", "G2", "GII", "ＧII"), 6),
    (("Ｇ１", "G1", "GI", "ＧI"), 7),
)


def class_ord(text: str | None) -> int | None:
    """クラス表記を序列に落とす。分からなければ None（回帰から外す）。"""
    if not text:
        return None
    t = text.strip()
    for words, v in reversed(_CLASS_ORD):     # Ｇ１ を 1勝 より先に見る
        if any(w in t for w in words):
            return v
    return None


def age_cond(text: str | None) -> str:
    """世代条件。'2'=2歳戦 / '3'=3歳限定 / 'old'=古馬混合。

    ⚠️ クラス序列（`class_ord`）だけでは **2歳新馬と3歳未勝利がどちらも0**に
       なってしまい、まったく違う時計水準が同じ扱いになる。交差検証で
       残差SD 1.251 → 1.193秒（−0.058秒）。回帰に入れた特徴のうち、
       効いたのはこれだけだった（当日馬場差・場×距離・頭数・牝馬限定は
       いずれも改善しないか悪化した）。
    """
    t = text or ""
    if "２歳" in t or "2歳" in t:
        return "2"
    if ("３歳" in t or "3歳" in t) and "上" not in t:
        return "3"
    return "old"


def before_date(runs, date: str | None):
    """**当日以降の行を落とす。**

    ⚠️ keibabook の馬DB成績には、**まだ走っていない当日のレースの行**が
       混ざっている（2026-08-01 中京2R の新馬全13頭に
       「2026-08-01 中京 芝1400 ２歳新馬」の行が入っていた）。
       これを過去走として食うと、
         * 出走馬全員が**同じ1行**を共有するので条件指数が全員同値になる
           （実際 中京1R が全馬+0.56、2R が全馬+1.64 になった）
         * 本来キャリア0の新馬に指数が付く
         * 結果を知っている行を回帰に入れることになる（リーク）
       例外も警告も出ない。**取得したら必ずこれを通すこと。**
    """
    if not date:
        return list(runs)
    return [r for r in runs if r.date and r.date < date]


def norm_surface(s: str | None) -> str | None:
    if not s:
        return None
    return "芝" if "芝" in s else ("ダ" if "ダ" in s else None)


def norm_baba(s: str | None) -> str:
    """'良'/'稍'/'重'/'不' に潰す。空は '良' 扱い。"""
    t = (s or "").strip()
    for k in ("不", "重", "稍"):
        if t.startswith(k):
            return k
    return "良"


# ---------------------------------------------------------------------------
# 第1段: 時計指数
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Cond:
    """勝ちタイムを説明するレース条件。"""

    surface: str
    distance: int
    place: str | None = None
    baba: str = "良"
    klass: int | None = None
    pace: str | None = None                # 'H'/'M'/'S'
    age: str = "old"                       # '2'/'3'/'old'

    @classmethod
    def of(cls, r: RunRecord) -> "Cond | None":
        s = norm_surface(r.surface)
        if not s or not r.distance:
            return None
        txt = f"{r.race_class or ''} {r.race_name or ''}"
        return cls(surface=s, distance=int(r.distance), place=r.place,
                   baba=norm_baba(r.baba), klass=class_ord(r.race_class or r.race_name),
                   pace=r.pace_mark, age=age_cond(txt))


def _solve(a: list[list[float]], b: list[float]) -> list[float] | None:
    """ガウス消去（部分ピボット）で a·x = b を解く。"""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(m[r][i]))
        if abs(m[p][i]) < 1e-12:
            return None
        m[i], m[p] = m[p], m[i]
        piv = m[i][i]
        for k in range(i, n + 1):
            m[i][k] /= piv
        for j in range(n):
            if j != i and m[j][i]:
                f = m[j][i]
                for k in range(i, n + 1):
                    m[j][k] -= f * m[i][k]
    return [m[i][n] for i in range(n)]


@dataclass
class TimeModel:
    """復元勝ちタイムを条件で説明する線形モデル。"""

    names: list[str]
    coef: list[float]
    places: list[str]
    resid_sd: float
    n: int
    use_pace: bool = True

    # -- 設計行列 ------------------------------------------------------------
    def _row(self, c: Cond) -> list[float]:
        d = c.distance / 1000.0
        turf = 1.0 if c.surface == "芝" else 0.0
        dirt = 1.0 - turf
        x = [1.0,
             turf * d, turf * d * d,
             dirt * d, dirt * d * d,
             dirt,
             turf * (c.baba == "稍"), turf * (c.baba == "重"), turf * (c.baba == "不"),
             dirt * (c.baba == "稍"), dirt * (c.baba == "重"), dirt * (c.baba == "不"),
             float(c.klass if c.klass is not None else 0),
             1.0 if c.klass is None else 0.0,          # クラス欠測フラグ
             1.0 if c.age == "2" else 0.0, 1.0 if c.age == "3" else 0.0]
        x += [1.0 if c.place == p else 0.0 for p in self.places[1:]]
        if self.use_pace:
            x += [1.0 if c.pace == "H" else 0.0, 1.0 if c.pace == "S" else 0.0]
        return [float(v) for v in x]

    @staticmethod
    def _names(places: list[str], use_pace: bool) -> list[str]:
        n = ["切片", "芝×距離", "芝×距離²", "ダ×距離", "ダ×距離²", "ダート",
             "芝稍", "芝重", "芝不", "ダ稍", "ダ重", "ダ不", "クラス", "クラス欠測",
             "2歳戦", "3歳限定"]
        n += [f"場:{p}" for p in places[1:]]
        if use_pace:
            n += ["ペースH", "ペースS"]
        return n

    # -- 学習 ----------------------------------------------------------------
    @classmethod
    def fit(cls, runs, *, use_pace: bool = True, ridge: float = 1e-3,
            before: str | None = None) -> "TimeModel | None":
        """出走各馬の過去走をまとめて放り込み、勝ちタイムの条件分解を推定する。

        ⚠️ 各レースは「そのレースを走った頭数」だけ重複して入る。同じレースを
           2頭が使っていれば同じ行が2回立つ。重複除去はレース単位で行う。
        """
        seen: dict[tuple, tuple[Cond, float]] = {}
        for r in before_date(runs, before):
            y = r.win_time_sec()
            c = Cond.of(r)
            if y is None or c is None or y <= 0:
                continue
            seen.setdefault((r.date, r.place, c.surface, c.distance), (c, y))
        rows = list(seen.values())
        places = sorted({c.place for c, _ in rows if c.place})
        if len(rows) < 20 or not places:
            return None

        model = cls(names=cls._names(places, use_pace), coef=[], places=places,
                    resid_sd=float("nan"), n=len(rows), use_pace=use_pace)
        xs = [model._row(c) for c, _ in rows]
        ys = [y for _, y in rows]
        p = len(xs[0])
        ata = [[sum(x[i] * x[j] for x in xs) + (ridge if i == j and i else 0.0)
                for j in range(p)] for i in range(p)]
        atb = [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(p)]
        coef = _solve(ata, atb)
        if coef is None:
            return None
        model.coef = coef
        res = [y - sum(c * v for c, v in zip(coef, x)) for x, y in zip(xs, ys)]
        dof = max(1, len(rows) - p)
        model.resid_sd = math.sqrt(sum(e * e for e in res) / dof)
        return model

    # -- 使う ----------------------------------------------------------------
    def predict(self, c: Cond) -> float:
        """その条件の「標準的な勝ちタイム」[秒]。"""
        return sum(a * v for a, v in zip(self.coef, self._row(c)))

    def fast(self, r: RunRecord) -> float | None:
        """**そのレース**が標準勝ち時計より何秒速かったか。プラスが速い。

        レースの質そのもの。同じレースを使った馬は着順に関わらず同値になる。
        """
        y = r.win_time_sec()
        c = Cond.of(r)
        if y is None or c is None:
            return None
        return self.predict(c) - y

    def fast_self(self, r: RunRecord, margin_weight: float = 1.0) -> float | None:
        """**その馬自身**が標準勝ち時計より何秒速く走ったか。プラスが速い。

        ＝ レースの速さ − 勝ち馬との着差。**着順ではなく自分の時計**を使う。
        5馬身離された馬でも、レースが速ければ良い数字になる。

        ⚠️ 当初は「自分の着順は使わない。10着でもレースが速ければ速い」という
           前提で `fast()` だけを使っていたが、**それだと順位付けの力がほぼ無い**。
           2026-08-01 中央27レースの実測（同じ土俵での比較）:

               指数の作り方          レース内スピアマン  条件1位の勝率/複勝率
               レースの勝ち時計            +0.095      15.0% / 30.0%
               自分の走破タイム            +0.319      25.0% / 60.0%
               着差を半分だけ              +0.222      25.0% / 50.0%
               （参考）単なる人気           +0.504

           速いレースに出ていたという事実だけでは足りない。**そこで自分が
           どれだけの時計で走ったか**が要る。南関のエンジンB（実測 複勝率67%）
           も自分の走破タイムを使っている。JRA版だけそれを捨てていた。
        """
        v = self.fast(r)
        if v is None or r.margin_sec is None:
            return None
        return v - r.margin_sec * margin_weight

    def baba_report(self) -> dict[str, float]:
        """健全性チェック用の馬場係数。

        芝は渋るほど遅い（稍・重ともプラス）／ダートは湿るほど速い（マイナス）
        が正しい向き。**逆に出た日は母数不足かパース漏れなので指数を信用しない。**
        """
        idx = {n: i for i, n in enumerate(self.names)}
        return {k: round(self.coef[idx[k]], 2)
                for k in ("芝稍", "芝重", "芝不", "ダ稍", "ダ重", "ダ不") if k in idx}

    def baba_sane(self) -> bool:
        b = self.baba_report()
        ok = True
        if "芝稍" in b and "芝重" in b:
            ok &= b["芝稍"] > 0 and b["芝重"] >= b["芝稍"]
        if "ダ稍" in b and "ダ重" in b:
            ok &= b["ダ稍"] < 0 and b["ダ重"] <= b["ダ稍"]
        return ok


# ---------------------------------------------------------------------------
# 第2段・第3段: 門とスコア
# ---------------------------------------------------------------------------

TOP_K = 2            # 条件指数に使う「良かった走」の本数
MIN_COND_RUNS = 2    # 条件指数を信用するのに要る最低走数
W_ANA = 0.5          # 人気薄好走1回あたり（手置き。sensitivity で妥当性を見る）
W_POP = 0.06         # 市場人気1つあたり（同上）
ANA_POP = 5          # 「人気薄」＝何番人気以下か
GATE_COND = 4        # ①条件順がこれ以内
GATE_POWER = 3       # ②実力順がこれ以内なら落とす
GATE_MARKET = 6.0    # ③市場人気がこれ以上（＝人気がない）
MIN_STABILITY = 0.50  # ①ノイズを乗せても条件上位に残る確率の下限


@dataclass
class Cand:
    umaban: int
    name: str
    cond_idx: float | None = None        # 今日の条件での上位2走平均[秒]＝ピーク
    cond_rank: int | None = None
    cond_runs: int = 0                   # 条件指数の材料になった走の数
    cond_ago: int | None = None          # ピークの走が何走前か（大きいほど市場は忘れている）
    power_idx: float | None = None       # 全走の中央値[秒]＝ふだんの水準
    power_rank: int | None = None
    n_runs: int = 0
    stability: float | None = None       # 条件順が上位に残る確率（ノイズ耐性）
    market: float | None = None          # 市場人気（当日人気順 or 近走平均人気）
    market_src: str = "-"
    ana_wins: int = 0                    # 人気薄での好走回数
    score: float | None = None
    gates: tuple[bool, bool, bool] = (False, False, False)
    note: str = ""

    @property
    def passed(self) -> bool:
        return all(self.gates)

    def why(self) -> str:
        if self.passed:
            return "通過"
        ng = [n for n, ok in zip("①②③", self.gates) if not ok]
        return "".join(ng) + "で落ち"


def peak(vals: list[float], k: int = TOP_K) -> float:
    """良かった走 上位k本の平均＝「今日の条件でのピーク」。

    ⚠️ **max を使ってはいけない。** max は残差ノイズの最大値を拾うので、
       走数の多い馬や、たまたま速い時計の出たレースを使っただけの馬が上に来る。

       検算（結果も市場も使わない再現性テスト）：同じ馬の過去走を奇数番目/
       偶数番目に割り、片方だけで作った指数ともう片方だけで作った指数の一致度を
       見た。**走数を揃えた150頭で max 0.298 に対し 上位2走の平均 0.484。**
       max は測っているものの半分がノイズだった。

       走数で縮小（`× n/(n+k)`）すると相関はさらに上がるが、これは**走数が
       両側に共通で入るだけの見かけの上昇**（走数を揃えると上位2走平均と
       完全に同値になる）。よって採用しない。走数の少なさは指数を歪めるのでは
       なく `Cand.cond_runs` で表に出し、門で弾く。
    """
    return mean(sorted(vals, reverse=True)[:k])


def _ana_wins(runs, *, ana_pop: int = ANA_POP) -> int:
    return sum(1 for r in runs
               if r.popularity and r.popularity >= ana_pop
               and r.finish_pos and r.finish_pos <= 3)


def market_of(entries: list[dict], *, recent: int = 3) -> dict:
    """市場側を出走馬ぜんぶまとめて作る。良い順に3段構え。

      1. 当日の人気（出馬表の「人気」欄）
      2. **単勝オッズの昇順順位** … 人気欄がまだ空でもオッズは先に入る。
         前日夕方の時点だと新潟・中京は人気欄が空でオッズだけ、という状態に
         なる（2026-08-02 の前日17時で実測）。オッズがあるなら順位は自分で
         作れるので、近走人気で代用する必要はない。
      3. 近走の平均人気 … オッズも無いとき（発売前）だけの最後の手段。

    ⚠️ 代用（3）は市場を見ていないのと同じ。どれを使ったかは必ず表示する。
    ⚠️ **レース確定後に取ると「確定人気」になる。** 事前予想として記録したい
       なら発走前に取ること。時計側は当日の行を落としてあるので汚れないが、
       市場側は取得時刻がそのまま結果に効く。

    return: {馬番: (値, 由来)}
    """
    out = {}
    pri = [e for e in entries if e.get("odds")]
    rank = {e["umaban"]: i for i, e in enumerate(
        sorted(pri, key=lambda e: e["odds"]), 1)}
    for e in entries:
        um = e["umaban"]
        if e.get("popularity"):
            out[um] = (float(e["popularity"]), "当日人気")
        elif um in rank:
            out[um] = (float(rank[um]), "オッズ順")
        else:
            ps = [r.popularity for r in e.get("runs", [])[:recent] if r.popularity]
            out[um] = ((round(mean(ps), 1), f"近{len(ps)}走人気") if ps else (None, "-"))
    return out


def evaluate(entries: list[dict], surface: str, *,
             w_ana: float = W_ANA, w_pop: float = W_POP,
             gate_cond: int = GATE_COND, gate_power: int = GATE_POWER,
             gate_market: float = GATE_MARKET,
             ana_pop: int = ANA_POP, power: str = "median",
             top_k: int = TOP_K, min_cond_runs: int = MIN_COND_RUNS,
             min_stability: float = MIN_STABILITY, draws: int = 400,
             basis: str = "self", margin_weight: float = 1.0,
             before: str | None = None,
             model: TimeModel | None = None) -> tuple[list[Cand], TimeModel | None]:
    """出走馬（`runs` に過去走を持つ dict のリスト）を評価して候補を返す。

    entries の各要素: {"umaban","name","runs":[RunRecord], "popularity":int|None}
    """
    allruns = [r for e in entries for r in before_date(e.get("runs", []), before)]
    model = model or TimeModel.fit(allruns)
    if model is None:
        return [], None

    mkt = market_of(entries)
    cands: list[Cand] = []
    for e in entries:
        runs = before_date(e.get("runs", []), before)
        vals = [(r, (model.fast(r) if basis == "race"
                     else model.fast_self(r, margin_weight))) for r in runs]
        vals = [(r, v) for r, v in vals if v is not None]
        cond = [(i, v) for i, (r, v) in enumerate(vals)
                if norm_surface(r.surface) == surface]
        allv = [v for _, v in vals]
        mk, src = mkt.get(e["umaban"], (None, "-"))
        best = sorted(cond, key=lambda iv: -iv[1])[:top_k]
        cands.append(Cand(
            umaban=e["umaban"], name=e.get("name", ""),
            cond_idx=(peak([v for _, v in cond], top_k)
                      if len(cond) >= min_cond_runs else None),
            cond_runs=len(cond),
            cond_ago=(best[0][0] + 1 if best else None),
            power_idx=((max(allv) if power == "max" else median(allv)) if allv else None),
            market=mk, market_src=src, ana_wins=_ana_wins(runs, ana_pop=ana_pop),
            n_runs=len(allv),
        ))

    # 順位付け。同値は「市場で安い方」を先に、最後は馬番で決める。
    def rank_by(key):
        def sk(c: Cand):
            v = getattr(c, key)
            return (v is not None, v if v is not None else -9e9,
                    c.market if c.market is not None else 0.0, -c.umaban)
        for i, c in enumerate(sorted(cands, key=sk, reverse=True), 1):
            setattr(c, key.replace("_idx", "_rank"), i)

    rank_by("cond_idx")
    rank_by("power_idx")

    stab = stability(entries, surface, model=model, gate_cond=gate_cond, top_k=top_k,
                     min_cond_runs=min_cond_runs, before=before, basis=basis,
                     margin_weight=margin_weight, draws=draws) if draws else {}
    for c in cands:
        c.stability = stab.get(c.umaban)
        g1 = (c.cond_rank is not None and c.cond_idx is not None
              and c.cond_rank <= gate_cond
              and (not draws or (c.stability or 0.0) >= min_stability))
        g2 = c.power_rank is None or c.power_rank > gate_power
        g3 = c.market is not None and c.market >= gate_market
        c.gates = (g1, g2, g3)
        if c.passed:
            c.score = round(c.cond_idx + w_ana * c.ana_wins + w_pop * c.market, 2)
    return cands, model


def stability(entries: list[dict], surface: str, *, model: TimeModel,
              gate_cond: int = GATE_COND, top_k: int = TOP_K,
              min_cond_runs: int = MIN_COND_RUNS, before: str | None = None,
              basis: str = "self", margin_weight: float = 1.0,
              draws: int = 400, seed: int = 7) -> dict[int, float]:
    """条件順が**ノイズに耐えるか**を測る。返り値は「条件順が上位に入る確率」。

    ⚠️ 残差SDは実測 1.15秒。ところがレース内の「条件4位までの幅」は 0.2〜1.0秒
       しかないことがほとんどで、**点推定の順位はたいていノイズ**。
       2026-08-01 の36レース中、幅が残差SDを超えたのは数レースだけだった。
       「条件3位だから買う」は、測定誤差の中で3位だったというだけ。

    そこで各走の指数に実測残差SDのゆらぎを乗せて何度も並べ直し、
    **上位に入り続ける馬だけを拾う**。走数の多い馬は平均で誤差が薄まるので
    自然に安定し、1〜2走しか材料が無い馬は落ちる。縮小推定を手で入れる
    代わりに、測った誤差そのものに順位を判定させる。
    """
    import random
    rng = random.Random(seed)
    sd = model.resid_sd
    pool: dict[int, list[float]] = {}
    for e in entries:
        vals = []
        for r in before_date(e.get("runs", []), before):
            if norm_surface(r.surface) != surface:
                continue
            v = (model.fast(r) if basis == "race"
                 else model.fast_self(r, margin_weight))
            if v is not None:
                vals.append(v)
        if len(vals) >= min_cond_runs:
            pool[e["umaban"]] = vals
    hit = {um: 0 for um in pool}
    for _ in range(draws):
        drawn = {um: peak([v + rng.gauss(0, sd) for v in vs], top_k)
                 for um, vs in pool.items()}
        for um in sorted(drawn, key=lambda u: -drawn[u])[:gate_cond]:
            hit[um] += 1
    return {um: h / draws for um, h in hit.items()}


def sensitivity(entries: list[dict], surface: str, *, model: TimeModel | None = None,
                w_ana=(0.25, 0.5, 1.0), w_pop=(0.03, 0.06, 0.12),
                **kw) -> tuple[dict[int, int], int]:
    """重みを振って ◎（スコア1位）が入れ替わるかを見る。

    手置きの 0.5 / 0.06 は回収率で最適化していない。だが**重みを2倍・半分に
    しても◎が変わらない**なら、その手置きは結論に影響していない、と言える。
    逆に入れ替わるなら、その日の◎は重みの産物なので信用しない。

    return: ({馬番: ◎になった回数}, 試した組み合わせ数)
    """
    if model is None:
        _, model = evaluate(entries, surface, **kw)
    if model is None:
        return {}, 0
    tally: dict[int, int] = {}
    n = 0
    for wa in w_ana:
        for wp in w_pop:
            cs, _ = evaluate(entries, surface, w_ana=wa, w_pop=wp, model=model, **kw)
            top = max((c for c in cs if c.passed),
                      key=lambda c: (c.score, -c.umaban), default=None)
            n += 1
            if top:
                tally[top.umaban] = tally.get(top.umaban, 0) + 1
    return tally, n
