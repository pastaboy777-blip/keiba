"""Mの法則（今井雅宏）の考え方を、南関のデータで使える形にしたもの。

⚠️ **これは今井雅宏氏の理論そのものではない。**公開されている用語集・解説から
   読み取った概念を、こちらが独自に南関のデータへ落とし込んだ実装。
   原典（書籍）は参照していないので、**本家と一致しない**。
   本家の指数を名乗らないこと。

── 理論の骨格（公開情報から）────────────────────────────────

今井雅宏氏が月刊誌「競馬王」で提唱した馬券術。著作に『Ｍより他に必勝法はなし』。

**M = Mind（精神）／ Minus（消耗）／ Mannerism（慣れと繰り返し）。**

    現代競馬はレベルの向上・インブリード・厩舎による人為的管理によって、
    **常にストレスを抱えた馬たちが競い合う**。そのストレスは甚大で、
    ほとんどの競走馬が胃潰瘍であることにも表れている。

⚠️⚠️ **だから「馬の絶対能力を測ることはナンセンス」**というのがこの理論の立場。
   いかに**新鮮な気持ちで走るか**が大事、とする。

   つまり本日このリポジトリで作った **BT値（絶対能力の指数）は、この理論が
   真っ向から否定するもの**である。どちらが正しいかはここでは決めない。
   ただし**同じ画面に並べるときは、別の前提に立った数字**だと分かるように
   すること。足したり掛けたりしない。

理論は3次元で構成される。

    横軸   … メンバー間の比較（**ストレス・疲労**）と、その中での異端性
    時間軸 … 馬の**近走のリズム**と、前走からのショック
    中心点 … 個々の馬のM3タイプ分け

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

── 実装している次元 ──────────────────────────────────────

    時間軸   `shocks()` `stiffness()` `rhythm()`  … ショック・硬直・近走のリズム
    横軸     `field_stress()` `fatigue()`         … 異端性・ペース圧力・**疲労のメンバー比**
    中心点   `m3()`                               … S／C／L の構造推定

⚠️ **疲労は絶対値ではなくメンバー比で見る。**横軸は「メンバー間の比較」なので、
   同じ中2週でも、周りが休み明けばかりなら疲れている側になる。

⚠️ **M3タイプは成績から推定しているだけ。**本家は馬体・気性・血統も見ている
   はずで、ここでは**走りの履歴に現れた癖**しか使っていない。別物と思うこと。
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


# ---------------------------------------------------------------------------
# 中心点 ── M3タイプ（S／C／L）の推定
# ---------------------------------------------------------------------------

#: M3の推定に要る最低走数。これ未満は判定しない（決めつけない）。
M3_MIN_RUNS = 5
#: 根幹距離（1600の倍数系）。C系が得意とされる。
KONKAN = (1600, 2000, 2400)
#: 多頭数／少頭数の境目。
BIG_FIELD = 12
SMALL_FIELD = 9
#: 惨敗とみなす相対着順。
ZANPAI = 0.6


@dataclass
class M3:
    """S（闘争心）／ C（集中力）／ L（淡白さ）の推定値。0〜1。

    ⚠️ **走りの履歴からの推定であって、本家の構造分析ではない。**
       本家は馬体・気性・血統も見る。ここにあるのは「結果に出た癖」だけ。

    ⚠️ **タイプ分けを目的にしない。**Mの法則の実践者自身が
       「目的は馬券をとることで、手段としてM3を用いる。目的がM3タイプ分けに
       なってしまったら意味がない」と言っている。ここでも M3 は
       **ショックの効き方を変えるための係数**として使い、単独では見ない。
    """

    s: float = 0.0
    c: float = 0.0
    l: float = 0.0
    n: int = 0
    #: 判定に効いた条件の数。0なら**材料が無い**（＝まとまり系ではない）。
    evidence: int = 0

    def label(self) -> str:
        """`S(L)` のように主構造＋（副構造）。3つが均等なら **M（まとまり系）**。

        ⚠️⚠️ **「材料が無い」と「まとまり系」を混同しないこと。**
           条件がばらけていない馬（いつも同じ距離・同じ頭数）は、得意条件から
           逆算できないので3つとも同じ値になる。それを正規化すると
           0.333 ずつになり、**まとまり系と見分けが付かなくなる**。
           実際そのバグを出した。`evidence` が0なら「―」を返す。
        """
        if self.n < M3_MIN_RUNS or self.evidence == 0:
            return "―"
        v = sorted((("S", self.s), ("C", self.c), ("L", self.l)),
                   key=lambda t: -t[1])
        if v[0][1] - v[2][1] < 0.15:
            return "M"                      # まとまり系
        main = v[0][0] + (v[1][0] if v[0][1] - v[1][1] < 0.10 else "")
        return f"{main}({v[2][0]})"

    def note(self) -> str:
        if self.n < M3_MIN_RUNS:
            return "走数不足で判定しない"
        if self.evidence == 0:
            return "条件が偏っていて判定できない（いつも同じ条件で走っている）"
        if self.label() == "M":
            return "まとまり系。無難にこなすが極限では通用しにくい"
        return {"S": "自分本位で走る。逃げ・短距離・距離短縮・特殊馬場が向く。連チャン期がある",
                "C": "相手との摩擦で集中する。格上げ・多頭数・内枠が向く。**休み明けと惨敗後は苦手**",
                "L": "自分のリズムで淡々と。格下げ・少頭数・外枠が向く。**休み明けと惨敗後の巻き返しが得意**",
                }[max((("S", self.s), ("C", self.c), ("L", self.l)),
                      key=lambda t: t[1])[0]]


def _rel(run) -> float | None:
    """相対着順（0=1着、1=最下位）。"""
    f, n = _g(run, "finish_pos"), _g(run, "field_size")
    return (f - 1) / max(1, n - 1) if (f and n and n > 1) else None


def _perf(runs, cond) -> float | None:
    """条件 `cond` に当てはまる走の相対着順の中央値。

    ⚠️ **走が「分かれた」ときだけ返す。**全走が該当する（または1走も該当しない）
       条件は、その馬の中で比較にならないので None を返す。実際そこを分けずに
       数えて、いつも同じ条件で走っている馬が「まとまり系」と判定される
       バグを出した。**該当2走以上、かつ非該当2走以上**を要求する。
    """
    hit = [x for x in (_rel(r) for r in runs if cond(r)) if x is not None]
    miss = [x for x in (_rel(r) for r in runs if not cond(r)) if x is not None]
    return median(hit) if (len(hit) >= 2 and len(miss) >= 2) else None


def m3(runs) -> M3:
    """過去走から S／C／L を推定する。**得意条件から逆算する。**

    本家が挙げる得意条件をそのまま判定材料にした。

        S（闘争心）… 逃げ・先行、短距離、距離短縮、特殊馬場（道悪）
        C（集中力）… 多頭数、内枠、格上げ。**休み明け・惨敗後は苦手**
        L（淡白さ）… 少頭数、外枠、非根幹距離。**休み明け・惨敗後の巻き返しが得意**

    ⚠️ 最初は「着順の分散」のような抽象的な量で測っていたが、それでは
       C と L がどちらも「安定」になって分離しなかった。**本家は得意条件を
       具体的に挙げている**ので、そこから逆算するほうが素直で当たる。
    """
    rs = [r for r in runs if _rel(r) is not None]
    if len(rs) < M3_MIN_RUNS:
        return M3(n=len(rs))
    base = median(x for x in (_rel(r) for r in rs) if x is not None)

    hits = [0]

    def edge(cond) -> float:
        """その条件で普段よりどれだけ走るか。プラスが得意。

        ⚠️ 「その条件で走ったことがない」と「走ったが差が無い」は別。
           前者は材料にならないので `hits` に数えない。
        """
        p = _perf(rs, cond)
        if p is None:
            return 0.0
        hits[0] += 1
        return max(-0.5, min(0.5, base - p))

    # S: 前で運ぶ癖 ＋ 短距離・短縮・道悪での上積み
    legs = [x for x in (leg(r) for r in rs) if x is not None]
    front = (1.0 - median(legs)) if legs else 0.5
    s_val = (0.55 * front
             + 0.45 * (0.5 + edge(lambda r: (_g(r, "distance") or 9999) <= 1300)
                       + edge(lambda r: (_g(r, "baba") or "").startswith(("重", "不")))))

    # C: 多頭数・内枠で上積み、休み明けと惨敗後で目減り
    c_val = (0.5
             + edge(lambda r: (_g(r, "field_size") or 0) >= BIG_FIELD)
             + edge(lambda r: _inner(r))
             - edge(lambda r: _after_rest(rs, r))
             - edge(lambda r: _after_zanpai(rs, r)))

    # L: 少頭数・外枠・非根幹距離で上積み、休み明けと惨敗後の巻き返しが得意
    l_val = (0.5
             + edge(lambda r: (_g(r, "field_size") or 99) <= SMALL_FIELD)
             + edge(lambda r: not _inner(r))
             + edge(lambda r: (_g(r, "distance") or 0) not in KONKAN)
             + edge(lambda r: _after_rest(rs, r))
             + edge(lambda r: _after_zanpai(rs, r)))

    n = max(1e-9, s_val + c_val + l_val)
    return M3(s=round(s_val / n, 3), c=round(c_val / n, 3),
              l=round(l_val / n, 3), n=len(rs), evidence=hits[0])


def _inner(run) -> bool:
    g, f = _g(run, "gate"), _g(run, "field_size")
    return bool(g and f and g <= f * INNER_FRAC)


def _after_rest(rs, run) -> bool:
    """その走が休み明けだったか。"""
    try:
        i = rs.index(run)
    except ValueError:
        return False
    if i + 1 >= len(rs):
        return False
    g = _days(_g(run, "date"), _g(rs[i + 1], "date"))
    return bool(g is not None and g >= REST_DAYS)


def _after_zanpai(rs, run) -> bool:
    """その走が惨敗の直後だったか。"""
    try:
        i = rs.index(run)
    except ValueError:
        return False
    if i + 1 >= len(rs):
        return False
    p = _rel(rs[i + 1])
    return bool(p is not None and p >= ZANPAI)


#: M3タイプごとの、ショックの効き方の倍率。⚠️ 未測定の初期値。
#: 本家が挙げる得意条件をそのまま倍率にしたもの。
SHOCK_FIT = {
    "休み明け": {"S": 1.0, "C": 0.4, "L": 1.6},   # C系は休み明けが苦手、L系は得意
    # ⚠️ 短縮は **S○・C○・L×**。L系は「ペースが速くなるとレースを投げ出す」ので
    #    向かない。C系はペースが速くなるぶん○。S系は気性を短縮で御せるので○。
    #    最初 C を 1.0（中立）にしていたのは読み込み不足だった。
    "短縮":     {"S": 1.5, "C": 1.3, "L": 0.6},
    "延長":     {"S": 0.7, "C": 0.8, "L": 1.3},   # 量のあるL系が延長に向く
    "内枠":     {"S": 1.0, "C": 1.4, "L": 0.7},   # C系は内枠、L系は外枠
}


def fit(tag: str, t: M3) -> float:
    """そのショックが、この馬のタイプにどれだけ効くか。1.0が標準。"""
    for k, w in SHOCK_FIT.items():
        if k in tag:
            if t.n < M3_MIN_RUNS:
                return 1.0
            top = max((("S", t.s), ("C", t.c), ("L", t.l)), key=lambda x: x[1])[0]
            return w[top]
    return 1.0


# ---------------------------------------------------------------------------
# 横軸 ── メンバー間のストレスと異端性
# ---------------------------------------------------------------------------

#: 異端の重み[点]。⚠️ 未測定の初期値。
I_ALONE = 1.5          # その条件に該当するのが自分だけ
I_FEW = 0.7            # 2頭だけ
#: 同型（先行馬）が何頭以上なら潰し合いとみなすか。
PRESSURE_N = 3


@dataclass
class FieldStress:
    """そのメンバーの中での立ち位置。"""

    ihen: float = 0.0                  # 異端性（浮いているほど高い）
    tags: list = field(default_factory=list)
    pressure: int = 0                  # 先行したい馬の数
    front_runner: bool = False         # 自分が先行型か

    def note(self) -> str:
        out = []
        if self.ihen >= 2.0:
            out.append("**異端**（メンバーの中で浮いている）")
        if self.pressure >= PRESSURE_N:
            out.append(f"前が潰れる形（先行型{self.pressure}頭）"
                       + ("・自分もそこ" if self.front_runner else "・差しに向く"))
        return " / ".join(out)


def field_stress(horses, date: str, place: str, distance: int | None
                 ) -> dict:
    """メンバー全体を見て、各馬の**異端性**と**ペース圧力**を出す。

    `horses` は `{名前: 過去走リスト}`。出馬表の全頭を渡すこと。

    ⚠️ **異端性は「1頭だけ違う」ことに意味がある。**半分が該当する条件は
       異端ではない。実際そこを分けずに数えると、ほぼ全頭に札が付いて
       選別にならない（点火指数で 62% に札が付いた失敗と同じ）。
       **該当が1〜2頭のときだけ加点する。**
    """
    feats: dict = {}
    for nm, runs in horses.items():
        prev = runs[0] if runs else None
        f = set()
        if prev:
            if _g(prev, "place") and _g(prev, "place") != place:
                f.add("他場帰り")
            gap = _days(date, _g(prev, "date"))
            if gap is not None and gap >= REST_DAYS:
                f.add("休み明け")
            pd = _g(prev, "distance")
            if pd and distance and pd > distance:
                f.add("短縮")
            elif pd and distance and pd < distance:
                f.add("延長")
            if is_gekiso(prev):
                f.add("前走激走")
        lp = leg(prev) if prev else None
        if lp is not None and lp <= 0.30:
            f.add("先行型")
        feats[nm] = f

    count: dict = {}
    for f in feats.values():
        for k in f:
            count[k] = count.get(k, 0) + 1

    pressure = count.get("先行型", 0)
    out = {}
    for nm, f in feats.items():
        sc, tags = 0.0, []
        for k in f:
            if k == "先行型":
                continue
            n = count[k]
            if n == 1:
                sc += I_ALONE
                tags.append(f"唯一の{k}")
            elif n == 2:
                sc += I_FEW
                tags.append(f"{k}（2頭だけ）")
        out[nm] = FieldStress(ihen=round(sc, 1), tags=tags,
                              pressure=pressure,
                              front_runner=("先行型" in f))
    return out


# ---------------------------------------------------------------------------
# 時間軸 ── 近走のリズム
# ---------------------------------------------------------------------------

#: 連闘・使い詰めとみなす間隔[日]。
TIGHT_DAYS = 20


def intervals(runs, date: str) -> list:
    """今回を含む直近の出走間隔[日]。新しい順。"""
    ds = [_g(r, "date") for r in runs if _g(r, "date")]
    if not ds:
        return []
    out = []
    prev = date
    for d in ds[:5]:
        g = _days(prev, d)
        if g is not None:
            out.append(g)
        prev = d
    return out


def rhythm(runs, date: str) -> tuple[str, str]:
    """近走の**リズム**（使われ方のパターン）を返す。(判定, 説明)。

    ⚠️ ショックが「前走から何が変わったか」の話なのに対し、リズムは
       **使われ方の流れ**の話。同じ中2週でも、ずっと詰めて使われた末の中2週と、
       休み明けからの中2週では意味が違う。ここを分けないとショックに埋もれる。
    """
    iv = intervals(runs, date)
    if len(iv) < 3:
        return "―", "走数不足でリズムは見ない"
    now, rest = iv[0], iv[1:]
    tight = sum(1 for x in rest if x <= TIGHT_DAYS)
    if now <= TIGHT_DAYS and tight >= len(rest) - 1:
        return "使い詰め", f"詰めて使われ続けている（{iv[:4]}日）"
    if now >= REST_DAYS and tight >= 2:
        return "一息入れた", f"使い詰めのあと間隔を空けた（{iv[:4]}日）"
    if now <= TIGHT_DAYS and tight == 0:
        return "詰めてきた", f"間隔を空けていたのを詰めてきた（{iv[:4]}日）"
    if max(iv) - min(iv) >= 45:
        return "不規則", f"使われ方が一定しない（{iv[:4]}日）"
    return "一定", f"リズムは崩れていない（{iv[:4]}日）"


# ---------------------------------------------------------------------------
# 横軸 ── 疲労（メンバー比）
# ---------------------------------------------------------------------------

#: 疲労を測る窓[日]。
FATIGUE_WINDOW = 90


def fatigue(runs, date: str) -> float:
    """**疲労の絶対量**。直近の出走密度から。大きいほど使われている。

    ⚠️ この値を単独で見ない。横軸は「メンバー間の比較」なので、
       `field_stress()` で**メンバーの中央値と比べて**初めて意味が出る。
       南関は使い詰めが普通なので、絶対値では全頭が「疲れている」になる。
    """
    n = 0
    for r in runs:
        g = _days(date, _g(r, "date"))
        if g is None:
            continue
        if g <= FATIGUE_WINDOW:
            # 近いほど重い（直線的に減衰）
            n += 1.0 - g / (FATIGUE_WINDOW * 1.2)
    return round(n, 2)


# ---------------------------------------------------------------------------
# 短縮ショッカー ── 本家が定義を明示している唯一の型
# ---------------------------------------------------------------------------

#: 3角で何番手以内なら「今走のスピードに付いていける」とみなすか。
SHOCKER_CORNER = 5
#: 同じ馬場種の経験を遡る月数。
SHOCKER_MONTHS = 7


def corner3(run) -> int | None:
    """3コーナーの通過順位。取れなければ None。

    ⚠️ 南関の通過順は距離によって2〜4点しかない。4点あれば後ろから2つめ、
       3点なら真ん中、2点なら最初、を3角とみなす。**位置決め打ちにしない。**
    """
    p = _g(run, "corner_pos") or []
    if len(p) >= 4:
        return p[-2]
    if len(p) == 3:
        return p[1]
    if len(p) >= 1:
        return p[0]
    return None


def tanshuku_shocker(distance: int | None, surface: str | None, date: str,
                     runs) -> tuple[str, list, list]:
    """**短縮ショッカー**の判定。(判定, 満たした条件, 欠けた条件)。

    本家の定義をそのまま実装した唯一の型。

        短縮ショッカー1
          ① 前走より今走の距離が短い
          ② 今走の距離以下で連対（2着以内）経験がある
          ③ 前走の3角が5番手以内
          ④ 7ヶ月以内に同じ馬場種のレースを経験している

        短縮ショッカー2（バウンド短縮）
          ① 前々走が今走と同距離・前走は今走より長い
          ②③④ は1と同じ（③は**前々走**の3角）

        両方満たすと **短縮ショッカーリミテッド**。破壊力はさらに増す。

    ②の意図は距離適性の確認、③の意図は「距離が短くなってペースが速くなっても
    付いていけるか」の確認。**距離が長い前走で前に行けるくらいのテンションが要る。**

    ⚠️ 短縮は基本的に**差し**とセット。逃げ馬で狙うのは、前走の距離が長すぎて
       逃げバテした後か、逃げられなかった逃げ馬のとき。
    ⚠️ M3では **L系は短縮に向かない**（ペースが速くなると投げ出す）。
    """
    if not distance or len(runs) < 1:
        return "", [], []
    prev = runs[0]
    prev2 = runs[1] if len(runs) > 1 else None

    ok2 = any(_g(r, "finish_pos") and _g(r, "finish_pos") <= 2
              and (_g(r, "distance") or 99999) <= distance for r in runs)
    ok4 = any(_days(date, _g(r, "date")) is not None
              and _days(date, _g(r, "date")) <= SHOCKER_MONTHS * 30
              for r in runs)

    def judge(c1: bool, c3run) -> tuple[bool, list, list]:
        c3 = corner3(c3run) if c3run is not None else None
        got, miss = [], []
        (got if c1 else miss).append("距離の形")
        (got if ok2 else miss).append("今走以下の距離で連対経験")
        (got if (c3 is not None and c3 <= SHOCKER_CORNER)
         else miss).append(f"3角{SHOCKER_CORNER}番手以内"
                           + (f"（実際{c3}）" if c3 else "（通過順なし）"))
        (got if ok4 else miss).append(f"{SHOCKER_MONTHS}ヶ月以内に同馬場種")
        return (not miss), got, miss

    pd = _g(prev, "distance")
    s1, g1, m1 = judge(bool(pd and pd > distance), prev)

    p2d = _g(prev2, "distance") if prev2 else None
    bound = bool(p2d and pd and p2d == distance and pd > distance)
    s2, g2, m2 = judge(bound, prev2)

    if s1 and s2:
        return "短縮ショッカーリミテッド", g1 + ["バウンド短縮でもある"], []
    if s1:
        return "短縮ショッカー1", g1, []
    if s2:
        return "短縮ショッカー2（バウンド短縮）", g2, []
    # 惜しい場合は何が欠けたかを返す（1のほうを基準にする）
    return "", g1, m1


def bound_shock(distance: int | None, runs) -> bool:
    """**バウンド式ショック**。前々走≒今走にして、前走で慣れを与えた形。

    「楽→苦→楽」の図式なので破壊力が増す、とされる。
    1600→1800→1600 のような並び。
    """
    if not distance or len(runs) < 2:
        return False
    a, b = _g(runs[1], "distance"), _g(runs[0], "distance")
    return bool(a and b and a == distance and b != distance)


# ---------------------------------------------------------------------------
# ストレス ── 疲労（肉体）とは別物
# ---------------------------------------------------------------------------

#: 接戦とみなす着差[秒]。
SESSEN_SEC = 0.3
#: 圧勝とみなす着差[秒]。
APPSHOU_SEC = 1.0

S_SESSEN = 1.5         # 接戦ストレス
S_OIKOMI = 1.0         # 追い込みストレス
S_SAME_DIST = 0.8      # 同距離ストレス
S_SAME_LINE = 1.2      # 同路線ストレス（メンバーが被る）


def stress(runs, field_prev_ids=None) -> tuple[float, list]:
    """**ストレス**（精神にかかる負担）。疲労（肉体）とは分けて持つ。

    種類（本家より）:
      同路線 … 前走と同じ馬が多く出走する。**着順が上の馬ほど影響が大きい**
      同距離 … 同じ距離が続く
      接戦   … 接戦だと馬は頑張ってしまい、**上位の馬に**ストレスが残る。
               ただし**勝ち馬は勝ったことで軽減される**
      追い込み … 直線に全精力を注ぎ込むのでストレスが発生する

    ⚠️ **圧勝するとほとんどストレスを貯めない。**そして
       「前走圧勝 → 今走格上げ挑戦」は主流路線の逆＝**異端路線**になるため、
       ストレスがなく鮮度が良い状態で走れる。**しばしば穴をあける形。**
       `atypical_upgrade()` で判定する。

    ⚠️ 疲労と混ぜないこと。**ハイペースのほうが疲労は大きい**が、
       それは肉体の話でストレスとは別軸。
    """
    if not runs:
        return 0.0, []
    last = runs[0]
    s, tags = 0.0, []
    fin, marg = _g(last, "finish_pos"), _g(last, "margin_sec")

    if marg is not None and fin:
        if fin == 1 and marg >= APPSHOU_SEC:
            tags.append(f"前走は圧勝（{marg}秒差）＝ストレスを貯めていない")
        elif marg <= SESSEN_SEC and fin <= 3:
            add = S_SESSEN * (0.5 if fin == 1 else 1.0)
            s += add
            tags.append(f"接戦ストレス（{marg}秒差で{fin}着）"
                        + ("・勝ち馬なので軽減" if fin == 1 else ""))

    p = _g(last, "corner_pos")
    f = _g(last, "field_size")
    if p and f and len(p) >= 2 and p[0] / f >= 0.7:
        s += S_OIKOMI
        tags.append("追い込みストレス（直線に全精力）")

    ds = [_g(r, "distance") for r in runs[:4] if _g(r, "distance")]
    if len(ds) >= 3 and len(set(ds)) == 1:
        s += S_SAME_DIST
        tags.append(f"同距離ストレス（{ds[0]}mが{len(ds)}走続き）")

    if field_prev_ids:
        n = sum(1 for x in field_prev_ids if x == _prev_id(last))
        if n >= 3:
            w = S_SAME_LINE * (1.3 if (fin or 99) <= 3 else 1.0)
            s += w
            tags.append(f"同路線ストレス（前走が同じレースの馬が{n}頭）"
                        + ("・上位だったので重い" if (fin or 99) <= 3 else ""))
    return round(s, 1), tags


def _prev_id(run) -> tuple:
    """前走レースの識別子（同路線の判定用）。"""
    return (_g(run, "date"), _g(run, "place"), _g(run, "distance"))


def atypical_upgrade(runs, race_class: str | None,
                     prev_class: str | None = None) -> tuple[bool, str]:
    """**前走圧勝 → 今走格上げ**。ストレスも疲労もない異端路線。

    本家が「しばしば穴をあける」と明示している形。さらに前走がスローなら
    疲労も無いので「次走は好走必至」とまで言われる。

    ⚠️ クラスの上下が取れないときは圧勝だけで判定する（弱くなる）。
    """
    if not runs:
        return False, ""
    last = runs[0]
    if _g(last, "finish_pos") != 1:
        return False, ""
    m = _g(last, "margin_sec")
    if m is None or m < APPSHOU_SEC:
        return False, ""
    return True, f"前走を{m}秒差で圧勝＝ストレスも疲労も無い"


# ---------------------------------------------------------------------------
# 延長ライダー ── 延長側の定義（短縮ショッカーの対）
# ---------------------------------------------------------------------------

#: 延長ライダーの「前走は後ろ」の閾値。
RIDER_BACK = 7


def enchou_rider(distance: int | None, date: str, runs) -> tuple[bool, list, list]:
    """**延長ライダー**の判定。(成立か, 満たした条件, 欠けた条件)。

        ① 前走で今走より**短い**距離を **3角7番手以降**で走っている
        ② 前々走で前走より**長い**距離を **3角5番手以内**で走っている
        ③ 前走より今走の距離のほうに実績がある
        ④ 7ヶ月以内に同じ馬場種のレースを経験している

    2000先行 → 1600差し → 今走2000、という**バウンド延長**の形。

    延長の効きどころは**ペースが緩むこと**。逃げ・先行とセットになりやすく、
    道中ゆったり行けて揉まれない。だから**揉まれ弱いL系が得意で、
    他馬との摩擦で走るC系は不得手**。

    ⚠️ **すべての延長がペース速→遅になるわけではない。**広いコースの短距離から
       小回りの中距離へ、のような臨戦では延長の利点が出ない。南関でも
       大井（大回り）から浦和（小回り）への延長は、緩くならない可能性がある。
       ここでは距離しか見ていないので、**コース形状は人が見ること。**
    """
    if not distance or len(runs) < 2:
        return False, [], ["走数不足"]
    prev, prev2 = runs[0], runs[1]
    pd, p2d = _g(prev, "distance"), _g(prev2, "distance")
    c1, c2 = corner3(prev), corner3(prev2)

    got, miss = [], []
    a = bool(pd and pd < distance and c1 is not None and c1 >= RIDER_BACK)
    (got if a else miss).append(f"前走は短い距離を3角{RIDER_BACK}番手以降"
                                + (f"（{pd}m・{c1}番手）" if pd else ""))
    b = bool(p2d and pd and p2d > pd and c2 is not None and c2 <= SHOCKER_CORNER)
    (got if b else miss).append(f"前々走は長い距離を3角{SHOCKER_CORNER}番手以内"
                                + (f"（{p2d}m・{c2}番手）" if p2d else ""))
    c = any((_g(r, "distance") or 0) >= distance and _g(r, "finish_pos")
            and _g(r, "finish_pos") <= 3 for r in runs)
    (got if c else miss).append("今走の距離側に実績")
    d = any(_days(date, _g(r, "date")) is not None
            and _days(date, _g(r, "date")) <= SHOCKER_MONTHS * 30 for r in runs)
    (got if d else miss).append(f"{SHOCKER_MONTHS}ヶ月以内に同馬場種")
    return (not miss), got, miss


# ---------------------------------------------------------------------------
# 同距離ショック ── 「一度失敗させてから同じ距離で狙う」
# ---------------------------------------------------------------------------

def same_distance_shock(distance: int | None, runs) -> tuple[str, str]:
    """**短縮後の同距離／延長後の同距離**。(種別, 説明)。

    距離は前走と変わらないので厳密にはショックではないが、好走の理由が
    **一連の距離変更の流れ**にあるので同じ枠で扱う。

    理屈が効く。未経験の距離への短縮を**一発目で決めるのは難しい**
    （ペースが速くて戸惑う）。だから**一度短縮して失敗させてから、
    次走の同距離で狙う**。負けても馬の精神状態は上向き、距離への慣れもできる。
    延長側も同じ。

    バウンドより破壊力は小さいが、**馬にかかる負担も小さい**。

    ⚠️ 前走で好走してしまっている場合はこの形ではない（それは既に決まった後）。
    """
    if not distance or len(runs) < 2:
        return "", ""
    pd, p2d = _g(runs[0], "distance"), _g(runs[1], "distance")
    if not pd or not p2d or pd != distance:
        return "", ""
    fin = _g(runs[0], "finish_pos")
    if fin and fin <= 3:
        return "", ""
    if p2d > distance:
        return "短縮後の同距離", f"{p2d}m→{distance}mで一度試して{fin}着、今回同距離2度目"
    if p2d < distance:
        return "延長後の同距離", f"{p2d}m→{distance}mで一度試して{fin}着、今回同距離2度目"
    return "", ""


# ---------------------------------------------------------------------------
# 逃げられなかった逃げ馬 ── 位置取りショックで最も破壊力が大きい形
# ---------------------------------------------------------------------------

#: 「逃げた」とみなす最初のコーナーの順位。
NIGE_POS = 1
#: 逃げ馬とみなすのに要る過去の逃げ回数。
NIGE_MIN = 2


def nigerarenakatta(runs, pressure: int | None = None) -> tuple[bool, str]:
    """**逃げられなかった逃げ馬**。位置取りショックで最も破壊力が大きいとされる形。

    前走で何らかの理由で逃げられず、今走は逃げられる、という図式。
    **逃げ馬は逃げられないというだけでストレスを感じる。**その辛い経験から
    一転して今走逃げられると、馬はものすごく楽に感じる。

    `pressure`（今回のメンバーの先行型の数）を渡すと、**今回逃げられそうか**まで
    見る。同型が多ければ今回も逃げられない可能性が高いので成立させない。

    ⚠️⚠️ **逃げられない＝単に活力が低下しているだけ、という可能性もある。**
       無闇に狙うのは禁物、と本家も釘を刺している。過去に何度も逃げている
       馬に限る（`NIGE_MIN` 回以上）ことで、そこを最低限ふるいにかけている。
    """
    if len(runs) < 3:
        return False, ""
    def head(r):
        p = _g(r, "corner_pos") or []
        return p[0] if p else None
    past = [head(r) for r in runs[1:]]
    n_nige = sum(1 for x in past if x is not None and x <= NIGE_POS)
    if n_nige < NIGE_MIN:
        return False, ""
    h = head(runs[0])
    if h is None or h <= 2:
        return False, ""
    if pressure is not None and pressure >= 3:
        return False, ""
    return True, (f"逃げられなかった逃げ馬（過去{n_nige}回逃げ／前走は{h}番手）"
                  + ("・今回は同型が少ない" if pressure is not None else ""))
