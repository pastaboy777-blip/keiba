"""BT値（南関版） ── 走破タイムから外部要因を剥がして能力を数値化する。

    BT値 = 中心値55 ＋ （基準タイム − 補正後タイム ＋ 年齢補正）÷ 距離係数 × 10

ユーザー提示の仕様（BigTime AI の実走BT値）を、**南関で取れるデータに合わせて**
実装したもの。中心値55＝古馬の中位条件で標準的な走り、というスケールを踏襲する。

実装した補正（Phase 1〜2）:
    基準タイム   … 場×距離×クラス×馬齢の4次元＋フォールバック（`BaseTime`）
    馬場比       … その日その場の前半／上がりを**2区間**で独立に測る
    斤量補正     … 標準斤量からの差 × 距離連続関数 × 高速馬場の二次補正
    年齢補正     … 月別の成長カーブ
    素点         … 距離係数で割って距離非依存にする

**まだ実装していない**（Phase 3以降）:
    ペース補正ブレンド／コース形態係数／不利補正／Cap・Floor／馬場状態補正

⚠️ **「馬ごとのテン3F が無いからペース補正は作れない」は誤りだった**（訂正）。
   確かに各馬の最初の600mは公開されていない。しかしペース補正が必要としているのは
   **「その馬が前半どれだけ脚を使ったか」**であって、区間が最初の3Fである必然性はない。
   南関では **前半 = 走破タイム − 上がり3F** が全87,097走で計算できる（100%）。
   差し馬は上がりが速い→前半が遅い→前半スコアが低い、と仕様どおりに動く。
   区間が「最初の3F」ではなく「上がり3F以外の全部」になるだけ。
   （この量は馬場比の計算で最初から使っていた。手元にあるのに無いと書いていた。）

⚠️ **本当に作れないのは不利補正だけ。** 南関の結果ページには「出遅れ」「不利」の
   記載が1件も無い（実測0件）。仕様の3層のうち**第2層・第3層は南関では不可**。
   中央（競馬ブック「発走状況他」）には有るので、そちらでは作れる。

⚠️ **コース形態係数は、この実装では要らない。** 仕様がそれを必要とするのは
   ペース判定を**全場共通の基準**でやっているから（中山芝1200mの下り坂スタートが
   ハイペースと誤検出される）。ここでは基準テン・基準上がりを
   **場×距離ごとに持っている**ので、坂や小回りの影響は基準側に吸収済み。

⚠️ 補正の係数は**まだ測っていない初期値**。仕様に書かれた値と一般的な相場から
   置いただけで、このデータで最適化したものではない。`scripts/bt_tune.py` で
   split-half（同じ馬・同条件で指数がどれだけ再現するか）で詰めること。
   **回収率でチューニングしない**（恒久ルール5・§32）。

⚠️ 「BT値が高い＝次も走る」ではない。これは**走った後の記録**であって予想ではない。

── 実測した性能（南関87,097走）─────────────────────────────

⚠️⚠️ **split-half の再現性で補正の価値を測ってはいけない。**
   同じ馬で値が安定するかを見るだけなので、**無補正の素の時計でも高く出る**。

       素の s/F（無補正）        r=+0.848
       基準との差だけ            r=+0.862
       ＋斤量・年齢              r=+0.871
       BT値（全補正）            r=+0.877      ← 補正の寄与は +0.029 しかない

   §32 と同じ罠。「毎日当たる予測は当たっても何も言っていない」。

**補正の本当の仕事は「条件をまたいで比べられること」**なので、そこで測る。
同じ馬が別の条件で走ったとき、値がどれだけ一致するか:

    別の競馬場どうし     素0.606 → BT **0.815**（+0.21・n=1,417頭）
    短距離と長距離       素0.532 → BT **0.729**（+0.20・n=901頭）
    良馬場と道悪         素0.863 → BT  0.878 （**+0.015 しかない**・n=4,470頭）

   **場と距離をまたぐ比較には効いている。道悪はほとんど効いていない。**
   しかも「基準との差だけ」(0.847) は**素の時計(0.863)より悪い**。基準を
   良馬場だけで作っているぶん道悪が系統的にずれ、馬場比が半分戻しているだけ。
   仕様の最終段「馬場状態補正（芝とダートで逆方向）」が未実装なのがここ。

⚠️⚠️ **前回書いた「ペース補正が無いせいで10.2点ずれる」は、測り方の産物だった。**
   あれはレースを**上がり水準**で瞬発戦／消耗戦に分けて測ったもの。上がりが速い
   レースは「ペースが遅い」だけでなく「格が高い・馬場が速い」ことも多いので、
   あの10.2点にはレースの格の差が丸ごと混ざっていた。

   **同じ馬**が、本当のペース形状（前半の比 − 上がりの比）をまたいで走ったときの
   差を測ると、**偏りは −1.35点しかない**（n=2,562頭）。桁が1つ違う。

   そのうえで仕様どおりのペース補正ブレンドを入れると **−1.54点に悪化した**。
   原因は分かっている。仕様の狙いは「同じレースの中で先行馬と追い込み馬を
   分ける」ことだが、この実装は各馬の区間タイムを**クラス基準**と比べているため、
   ハイペースのレースでは**全頭の前半が速く出て全頭が加点される**。
   レース内の差をつけるには、区間スコアを**そのレース自身の区間タイム**と
   比べる必要がある。そこは未着手。

   **したがって既定でオフ**（`PACE_BLEND_ON = False`）。1.35点のために
   悪化する補正は入れない。コードは研究用に残してある。

⚠️ 脚質の偏り（3着内馬で 前53.2 / 中51.1 / 後50.4）は残っている。ただしこれも
   「前が有利な馬場だから前の馬が実際に速く走った」のか「展開の恩恵を能力と
   誤認している」のかは、この実装では分離できない。

**馬場状態補正は効いた。**同じ馬の良馬場との差:

    補正前  稍 −0.60 / 重 −1.15 / 不 −2.36 点
    補正後  稍 −0.00 / 重 −0.02 / 不 −0.00 点   ← 偏りが消えた

   ⚠️ ただし**相関では効果が見えない**（0.878 → 0.879）。各群に定数を足す
      補正なので、相関は原理的にほとんど動かない。**偏りを消す補正は
      偏りで測ること。** 相関で測って「効かなかった」と判断しかけた。

⚠️⚠️ **一致度（相関）で係数を決めてはいけない。**斤量係数でこれに引っかかった。

    斤量係数        補正後に残る偏り      場をまたいだ一致度
    補正なし        -0.215 BT点/kg       +0.798
    実測値 0.0227   **+0.004**（正解）    +0.798
    旧値 ≒0.10      +0.748（効かせすぎ）   **+0.815** ← 一致度は「良い」

   一致度は**間違った係数のほうを好んだ**。理由は、斤量は性別と結びついていて
   （牝馬は2kg軽い）、係数を大きくすると牝馬と牡馬の差が広がるから
   （同じレース内で 牝−牡 が -2.12点 → -3.69点）。**馬ごとに安定した差を
   誇張すると、馬の間のばらつきが増えて相関は機械的に上がる。**
   split-half が無補正でも高く出たのと同じ構造で、相関は「広がり」を
   評価しているのであって「正確さ」ではない。

   **係数は残差で決める。**「補正した後にその変数の効果が0になっているか」だけが
   直接の答えで、下流の相関がどう動くかは判断材料にしない。

**使ってよい範囲**: 場や距離をまたいだ能力比較。
**使ってはいけない範囲**: 道悪の走りを良馬場の走りと並べる／
    スローの瞬発戦で出た数字と消耗戦で出た数字を同列に扱う。
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median

#: BT値の中心。古馬の中位条件で標準的な走りをした馬がこのあたり。
CENTER = 55.0
#: 距離係数の下限。短距離はペース・スタートのノイズがタイムに占める比率が
#: 大きいので、そのまま距離で割るとノイズまで増幅される（仕様の指示）。
DIST_COEF_FLOOR = 1.2
#: 基準タイムを1マスに作るのに要る最低サンプル数。
MIN_SAMPLES = 8
#: 基準タイムのサンプルに使う着順の上位割合（1着は除く。仕様どおり）。
SAMPLE_TOP_FRAC = 0.33
#: **採点に使う統一クラス**。仕様の「古馬MIDDLE」に相当する南関の中位条件。
SCORE_CLASS = "C2"

#: 馬場状態ごとの最終補正[BT点]。**実測値**（同じ馬の良馬場での値との差）。
#:
#: ⚠️ 当日馬場比だけでは道悪を吸収しきれない。濡れたダートは速いので馬場比が
#:    1.0を下回り、その割り戻しで**時計を過剰に割り引いてしまう**。同じ馬で
#:    比べると 稍 −0.60 / 重 −1.15 / 不 −2.36 と系統的に低く出ていた
#:    （n=4,350 / 3,427 / 1,926頭）。その分をここで戻す。
#:
#: ⚠️ 仕様は「ダートは重・不良でBT値が**高く**出る」と書いているが、南関の実測は
#:    **逆**だった。仕様の実装は当日馬場比を持たないのだと思われる。
#:    **仕様の符号をそのまま持ち込まないこと。**
BABA_ADJ = {"良": 0.0, "稍": 0.60, "重": 1.15, "不": 2.36}


def norm_baba(baba: str | None) -> str | None:
    """'稍重' → '稍' / '不良' → '不'。取れなければ None。"""
    b = baba or ""
    for k in ("良", "稍", "重", "不"):
        if b.startswith(k):
            return k
    return None

# ---------------------------------------------------------------------------
# クラス
# ---------------------------------------------------------------------------

#: 南関のクラス表記 → 階級。細分（Ｃ２三四 の「三四」）は落とす。
_CLS_RE = re.compile(r"([ＡＢＣ][１-３]|[２-４]歳|オープン|重賞)")


def grade(race_class: str | None) -> str | None:
    """'Ｃ１三' → 'Ｃ１' / 'Ｂ１二Ｂ２一' → 'Ｂ１' / '３歳２' → '３歳'。

    併合クラス（Ｂ１二Ｂ２一）は**上の級**で代表させる。下の級に合わせると
    レース水準を過小評価するため。
    """
    if not race_class:
        return None
    ms = _CLS_RE.findall(race_class)
    return ms[0] if ms else None


#: par を作るときの束ね方。1マスあたり最低8走を確保するため上級を潰す。
_PAR_BUNDLE = {"オープン": "A+", "重賞": "A+", "Ａ１": "A+", "Ａ２": "A+", "Ａ３": "A+",
               "Ｂ１": "B", "Ｂ２": "B", "Ｂ３": "B",
               "Ｃ１": "C1", "Ｃ２": "C2", "Ｃ３": "C3",
               "２歳": "2yo", "３歳": "3yo", "４歳": "B"}


def par_key(race_class: str | None) -> str:
    """基準タイムのマス用のクラス鍵。

    ⚠️ **Ａ級以上は 'A+' に束ねる。**南関でＡ１・Ａ２・オープンを別々に持つと
       1マスあたりのレース数が1桁になり、基準タイムが1〜2走のブレで動く。
       §31 で「par にクラスを入れていなかった」件の是正だが、入れれば良いという
       ものではなく、**束ね方まで含めて1組**であること。
    """
    return _PAR_BUNDLE.get(grade(race_class) or "", "other")


def age_group(age: int | None) -> str:
    """'2' / '3' / 'old'。年齢が無ければ 'old' に寄せる。"""
    if age == 2:
        return "2"
    if age == 3:
        return "3"
    return "old"


# ---------------------------------------------------------------------------
# 基準タイム
# ---------------------------------------------------------------------------

def ten3f_ok(distance: int | None) -> bool:
    """テン3F を信用してよい距離か（200で割り切れること）。

    ⚠️ 1500m・1900m は先頭に100mの半端な区間が入るのでハロン割りがずれる。
    """
    return bool(distance) and distance % 200 == 0


def is_sample(row: dict, *, lane_frac: float = 0.5) -> bool:
    """基準タイムのサンプルに採ってよい1走か。

    仕様の条件を南関に移したもの:
      * 良馬場のみ
      * **1着を除いた**上位 SAMPLE_TOP_FRAC（桁違いに強い馬が下級条件に
        出てきたときに基準が不当に速くなるのを防ぐ）
      * ハンデ戦を除く（能力に応じた斤量設定なので斤量補正の前提が崩れる）
      * 見習い騎手を除く（減量でタイムが歪む）
      * ロスの少ない馬に限る

    ⚠️ 仕様の「4角中レーン以内」は**南関では再現できない**。レーン（内/中/外）の
       データが公開されていないため、**4角が頭数の半分以内**で代用している。
       これは「外を回っていない」ではなく「後方でロスしていない」の代理であって、
       別物であることを忘れないこと。
    """
    if not (row.get("baba") or "").startswith("良"):
        return False
    if not row.get("time_sec") or not row.get("finish"):
        return False
    if row.get("apprentice"):
        return False
    if "ハンデ" in (row.get("condition") or ""):
        return False
    fld = row.get("field_size") or 0
    if row["finish"] == 1 or row["finish"] > max(2, round(fld * SAMPLE_TOP_FRAC)):
        return False
    c4 = row.get("corner4")
    if c4 is not None and fld and c4 > max(3, fld * lane_frac):
        return False
    return True


@dataclass
class BaseTime:
    """場×距離×クラス×馬齢 の基準タイム表。

    `win` は「その条件で標準的な馬が良馬場で走ったときの走破タイム[秒]」。
    `ten` / `last` は同じ母集団でのレースのテン3F・上がり3F。
    """

    win: dict = field(default_factory=dict)
    ten: dict = field(default_factory=dict)
    last: dict = field(default_factory=dict)
    n: dict = field(default_factory=dict)

    # --- 構築 -------------------------------------------------------------
    @classmethod
    def build(cls, rows, *, min_samples: int = MIN_SAMPLES) -> "BaseTime":
        """1頭1行のレコード列から基準タイム表を作る。"""
        t: dict = defaultdict(list)
        races: dict = defaultdict(dict)          # 区間はレース単位で1回だけ
        for r in rows:
            if not is_sample(r):
                continue
            k = (r["place"], r["distance"], par_key(r.get("race_class")),
                 age_group(r.get("age")))
            t[k].append(r["time_sec"])
            races[k][r["rid"]] = r
        self = cls()
        for k, v in t.items():
            if len(v) < min_samples:
                continue
            self.win[k] = round(median(v), 2)
            self.n[k] = len(v)
            rs = list(races[k].values())
            lt = [x["last3f_race"] for x in rs if x.get("last3f_race")]
            tn = [x["ten3f"] for x in rs if x.get("ten3f") and ten3f_ok(x["distance"])]
            if lt:
                self.last[k] = round(median(lt), 2)
            if tn:
                self.ten[k] = round(median(tn), 2)
        return self

    # --- 参照 -------------------------------------------------------------
    def lookup(self, place: str, distance: int, race_class: str | None,
               age: int | None) -> tuple[float | None, float | None, str]:
        """(基準走破タイム, 基準上がり3F, どの段で当たったか) を返す。

        フォールバックの順（仕様の6段を南関の4次元に合わせて4段に）:
          1. 同場・同距離・同クラス・同馬齢
          2. 同場・同距離・同クラス・古馬
          3. 同場・同距離・全クラス統合・古馬
          4. 同場・同距離のうち一番サンプルの多いマス

        ⚠️ **どの段で当たったかを必ず持ち回ること。**3段・4段まで落ちた
           BT値は「その条件の基準」ではなく「近い条件の基準」で出した値で、
           精度が違う。出力から段を消すと、後で誰も区別できなくなる。
        """
        pk = par_key(race_class)
        ag = age_group(age)
        for key, level in (((place, distance, pk, ag), "1:完全一致"),
                           ((place, distance, pk, "old"), "2:古馬で代用"),
                           ((place, distance, "C2", "old"), "3:中位クラスで代用")):
            if key in self.win:
                return self.win[key], self.last.get(key), level
        cand = [(n, k) for k, n in self.n.items()
                if k[0] == place and k[1] == distance]
        if cand:
            k = max(cand)[1]
            return self.win[k], self.last.get(k), "4:同距離の最大マスで代用"
        return None, None, "5:該当なし"

    def unified(self, place: str, distance: int
                ) -> tuple[float | None, float | None, str]:
        """**採点に使う統一基準**（古馬の中位条件）を返す。

        ⚠️⚠️ **採点にクラス別の基準を使ってはいけない。**使うと、どのクラスの
           馬も自分のクラスの基準と比べられるので、**全クラスが55に寄って
           指数が階級を区別しなくなる**。実際 浦和1400m の基準は
           A+ 87.6 / C3 92.4 と 4.8秒 も違うのに、それぞれを自分の基準で
           測れば両方とも55になってしまう。

           仕様も同じことを言っている ——「クラスごとに異なる基準タイムを
           使うと、新馬戦で出したBT値とOP戦で出したBT値が別々のスケールに
           なる」。だから採点は **古馬中位（南関ではＣ２）に固定**する。

           一方、**馬場比はクラス別の基準で測る**（`lookup`）。そうしないと、
           下級条件ばかりの日が「時計のかかる馬場」に見えてしまう。
           採点は統一・馬場比は条件別、で1組。
        """
        for key, level in (((place, distance, SCORE_CLASS, "old"), "1:統一基準"),
                           ((place, distance, "C1", "old"), "2:C1で代用"),
                           ((place, distance, "B", "old"), "3:Bで代用")):
            if key in self.win:
                return self.win[key], self.last.get(key), level
        cand = [(n, k) for k, n in self.n.items()
                if k[0] == place and k[1] == distance and k[3] == "old"]
        if cand:
            k = max(cand)[1]
            return self.win[k], self.last.get(k), "4:同距離の最大マスで代用"
        return None, None, "5:該当なし"

    # --- 保存 -------------------------------------------------------------
    def dump(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({name: {"|".join(map(str, k)): v for k, v in d.items()}
                       for name, d in (("win", self.win), ("ten", self.ten),
                                       ("last", self.last), ("n", self.n))},
                      f, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "BaseTime":
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        def un(d):
            out = {}
            for k, v in d.items():
                p, di, pk, ag = k.split("|")
                out[(p, int(di), pk, ag)] = v
            return out
        return cls(win=un(raw["win"]), ten=un(raw["ten"]),
                   last=un(raw["last"]), n=un(raw["n"]))


# ---------------------------------------------------------------------------
# 馬場比（当日・2区間）
# ---------------------------------------------------------------------------

@dataclass
class TrackRatio:
    """その日その場の馬場の速さ。**1.0未満が高速馬場**（基準より速い）。

    ⚠️ 仕様は前3F・中間・後3F の**3区間独立**だが、南関では
       **馬ごとの区間タイムが上がり3Fしか無い**ので、
       「前半（走破−上がり3F）」と「上がり3F」の**2区間**に落としている。
       レース単位なら先頭ラップから3区間に割れるが、馬ごとに割れない以上、
       3区間にしても補正に使えない。ここは仕様どおりではない。
    """

    early: float = 1.0
    late: float = 1.0
    n_races: int = 0

    @property
    def label(self) -> str:
        m = (self.early + self.late) / 2
        return ("高速馬場" if m < 0.99 else "時計のかかる馬場" if m > 1.01 else "標準")


def day_ratio(day_rows, base: BaseTime, *, min_races: int = 3) -> TrackRatio:
    """同じ日・同じ場の全レースから馬場比を測る。

    各レースの「勝ち時計の前半」「レースの上がり3F」を、その条件の基準と比べ、
    比の中央値を取る。距離が混ざっても**比**なので揃う。
    """
    e, l = [], []
    seen = set()
    for r in day_rows:
        if r["rid"] in seen or not r.get("win_time"):
            continue
        seen.add(r["rid"])
        # ⚠️ 馬場比は**クラス別の基準**で測る。年齢は馬ではなくレース条件から
        #    決める（1行目の馬の年齢を使うと、同じレースでも引く基準が変わる）。
        pk = par_key(r.get("race_class"))
        ra = 2 if pk == "2yo" else 3 if pk == "3yo" else None
        bw, bl, _ = base.lookup(r["place"], r["distance"],
                                r.get("race_class"), ra)
        rl = r.get("last3f_race")
        if not bw or not bl or not rl:
            continue
        be = bw - bl
        ae = r["win_time"] - rl
        if be > 0 and ae > 0:
            e.append(ae / be)
            l.append(rl / bl)
    if len(e) < min_races:
        return TrackRatio(1.0, 1.0, len(e))
    return TrackRatio(round(median(e), 4), round(median(l), 4), len(e))


# ---------------------------------------------------------------------------
# 斤量補正
# ---------------------------------------------------------------------------

#: **牡馬定量**[kg]。南関87,097走の実測最頻値から。
#: 牝馬は 3歳・古馬とも 54.0 が最頻で、牡馬より2kg軽い。この2kgを
#: 「補正すべき差」として扱うのが仕様の考え方なので、**牡馬の値を基準に置く**。
#: 2歳だけは牡も牝も54.0で差が無い（南関では2歳に牝馬減量が無い）。
STD_KINRYO = {"2": 54.0, "3": 56.0, "old": 56.0}

#: 斤量1kgあたりの秒数（**1000mあたり**）。同じ馬・同じクラスの中で実測した値。
#:
#: ⚠️ **効果は距離に比例する**（一定の秒数ではない）。重い斤量は「1kmあたり
#:    何秒遅くなる」という形で効くので、距離を掛ける。最初は距離によらない
#:    固定秒＋距離倍率という形にしていたが、これは構造から間違いだった。
#:
#: ⚠️ **初期値（実効0.10秒/kg/1000m相当）は実測の約4倍で過大だった。**
#:    仕様や巷の「1kg＝0.1〜0.2秒」をそのまま持ち込むと効かせすぎる。
#:    実測（同じ馬の中で斤量が動いたときだけを見る）:
#:        同じ馬                    +0.0552
#:        同じ馬×同じクラス          +0.0227   ← これを採用
#:        同じ馬×同じクラス×同じ距離  +0.0171
#:    絞るほど小さくなる。緩いほうは「クラスが上がると斤量も上がる」交絡を
#:    含み、きついほうは残る変動が少なく過小に出やすい。中間を取った。
#:
#: ⚠️ 別定は**強い馬ほど重い**ので、素直に回帰すると符号が逆に出る。
#:    必ず**同じ馬の中で**（馬を固定して）測ること。
SEC_PER_KG_1000M = 0.0227

#: 距離ごとの効きの違い。**実測では出なかったので一律1.0**。
#:
#: ⚠️ 仕様は「短距離ほど斤量の物理的影響が大きい」として距離連続関数を
#:    置いているが、南関の実測はそうならなかった:
#:        〜1100m +0.0083 ／ 1200〜1400m +0.0246
#:        1500〜1700m +0.0170 ／ 1800m〜 +0.0391
#:    単調でないどころか、長距離のほうが大きい。1000mあたりに正規化した
#:    時点で距離の効果は吸収済み、と読むのが素直。**仕様の形を残さない。**
_DIST_ANCHOR = ((800, 1.0), (2600, 1.0))

#: 騎手ランクごとの倍率。**実測では出なかったので一律1.0**。
#:
#: ⚠️ 仕様は「リーディング上位は斤量差を技術でカバーできるので係数が小さい」
#:    としているが、南関の実測は**まったく単調でなく、むしろ逆向き**だった:
#:        ランク1 +0.0365 ／ 2 +0.0452 ／ 3 -0.0026
#:        ランク4 +0.0341 ／ 5 +0.0424 ／ 見習い +0.0315
#:    ランク3が負に出る時点でノイズ。**根拠が無いので係数を入れない。**
#:    引数は残してあるので、測れたら埋めればよい。
JOCKEY_MULT = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0}

#: 高速馬場での二次補正の強さ。⚠️ **未測定**。仕様に沿って置いただけ。
FAST_TRACK_K = 1.5


def dist_mult(distance: int) -> float:
    """距離ごとの効き。アンカー間を線形補間する（現状はどこでも1.0）。"""
    a = _DIST_ANCHOR
    if distance <= a[0][0]:
        return a[0][1]
    if distance >= a[-1][0]:
        return a[-1][1]
    for (d0, m0), (d1, m1) in zip(a, a[1:]):
        if d0 <= distance <= d1:
            return m0 + (m1 - m0) * (distance - d0) / (d1 - d0)
    return 1.0


def weight_sec(kinryo: float | None, age: int | None, distance: int,
               *, jockey_rank: int = 3, ratio: float = 1.0) -> float:
    """標準斤量からの差を秒に直す。**プラスなら「重い斤量を背負っていた」**。

    返り値を走破タイムから引くと、標準斤量で走った場合の時計に近づく。
    **距離に比例する**（1000mあたりの秒数×距離）。
    """
    if not kinryo:
        return 0.0
    d = kinryo - STD_KINRYO[age_group(age)]
    k = (SEC_PER_KG_1000M * (distance / 1000.0)
         * dist_mult(distance) * JOCKEY_MULT.get(jockey_rank, 1.0))
    if ratio < 1.0:                       # 高速馬場では体重差が推進力差に直結
        k *= 1.0 + FAST_TRACK_K * (1.0 - ratio) ** 2
    return d * k


# ---------------------------------------------------------------------------
# 年齢補正
# ---------------------------------------------------------------------------

#: 1000mあたりの年齢補正[秒]。**南関1,866走の実測値**（推測値ではない）。
#: 古馬中位（Ｃ２）の統一基準に対して、その年齢のクラス標準がどれだけ遅いか。
_AGE_CURVE = {
    2: {m: 0.64 for m in range(1, 13)},
    3: {1: 0.80, 2: 0.80, 3: 0.80,
        4: 0.00, 5: 0.00, 6: 0.00,
        7: 0.10, 8: 0.10, 9: 0.10,
        10: 0.35, 11: 0.35, 12: 0.35},
}


def age_sec(age: int | None, date: str, distance: int) -> float:
    """年齢補正。古馬は0。**距離に比例させる**（s/1000m で持つ）。

    ⚠️⚠️ **仕様の「月別の成長カーブ」は、このデータでは再現できなかった。**
       南関1年ぶんで実測した月別の値は

           2歳  5月+0.52 6月+0.64 7月+0.71 8月+0.71 9月+0.73
                10月+1.07 11月+0.69 12月+0.47   （通年 +0.64 / n=577）
           3歳  1月+0.93 2月+0.29 3月+1.21 4月+0.14 5月+0.07 6月−0.22
                7月+0.03 8月+0.08 9月+0.19 10月+0.71 11月+0.14 12月+0.35
                                              （通年 +0.33 / n=1289）

       で、**月を追うごとに古馬に近づくという単調な形になっていない**。
       2歳は逆に秋にかけて広がって見えるし、3歳の10月だけ跳ねる（n=49）。
       月別に細かく持つと、このノイズをそのまま指数に焼き込むことになる。

       そこで **2歳は通年一定、3歳は四半期** に落とした。3歳の1〜3月が
       他より0.8秒/1000m 遅いのは、年が明けて3歳になった直後＝実質2歳の
       延長だからで、これは月別で唯一はっきり出ている構造なので残した。

    ⚠️ 最初は仕様の形（2歳6月2.5 → 3歳12月0.0）を推測で置いていたが、
       **実測の4倍近く過大**だった（2歳9月で2.1 対 実測0.73）。
       仕様の数値をそのまま持ち込まないこと。
    """
    if age not in _AGE_CURVE:
        return 0.0
    try:
        month = int(date.split("-")[1])
    except (IndexError, ValueError):
        return 0.0
    return _AGE_CURVE[age].get(month, 0.0) * distance / 1000.0


# ---------------------------------------------------------------------------
# 素点
# ---------------------------------------------------------------------------

def dist_coef(distance: int) -> float:
    """距離係数。同じ能力差が同じポイント差になるように割る。"""
    return max(distance / 1000.0, DIST_COEF_FLOOR)


#: ⚠️ **ペース補正ブレンドは既定でオフ。**実測で効果が無く、むしろ悪化した。
#:    詳細はモジュール冒頭の「実測した性能」を読むこと。研究用に残してある。
PACE_BLEND_ON = False
#: ペース補正ブレンドの上限。これ以上は区間スコアに寄せない（仕様も上限を置く）。
BLEND_MAX = 0.45
#: ペースのズレ（前半が基準から何%ずれたか）1あたりのブレンド率。
BLEND_K = 4.0
#: これ未満のズレはペースと見なさない（不感帯）。
BLEND_DEAD = 0.010
#: 斤量補正の区間配分。スタート〜加速のほうが重量の影響を受けやすい（仕様）。
KIN_SPLIT_EARLY = 0.70


@dataclass
class BTResult:
    bt: float
    base: float
    adjusted: float
    gap: float
    level: str
    ratio: TrackRatio
    parts: dict


def pace_dev(row: dict, base_win: float, base_late: float) -> float | None:
    """そのレースのペースのズレ。**マイナスがハイペース**（前半が基準より速い）。

    レースの前半（勝ち時計 − レースの上がり3F）が、その条件の基準の前半から
    何割ずれたか。**場×距離ごとの基準と比べる**ので、下り坂スタートで
    構造的にテンが速いコースを「ハイペース」と誤検出しない
    （仕様がコース形態係数で吸収している部分は、基準側に入っている）。
    """
    rl = row.get("last3f_race")
    wt = row.get("win_time")
    if not rl or not wt or not base_late:
        return None
    be = base_win - base_late
    ae = wt - rl
    if be <= 0 or ae <= 0:
        return None
    # ⚠️ **前半の基準からのズレだけを見てはいけない。**前半も上がりも同じ
    #    走破タイムから来るので、レース全体が速いだけでも前半は速く出る。
    #    実際それで判定したら 瞬発戦 −0.0140 / 消耗戦 −0.0134 と**まったく
    #    区別できていなかった**（ペースではなくレースの格を測っていた）。
    #    **前半の比と上がりの比の差**を取れば全体の速さが打ち消え、
    #    「前半と後半のどちらに寄った流れか」だけが残る。
    return ae / be - rl / base_late


def score(row: dict, base: BaseTime, ratio: TrackRatio,
          *, jockey_rank: int = 3, pace: bool = PACE_BLEND_ON,
          baba: bool = True) -> BTResult | None:
    """1頭の1走を BT値にする。基準タイムが引けなければ None。

    `pace=False` / `baba=False` で個々の補正を切れる（効果測定用）。
    """
    t = row.get("time_sec")
    if not t:
        return None
    bw, bl, level = base.unified(row["place"], row["distance"])
    if not bw:
        return None
    di = row["distance"]
    ag = row.get("agari")
    w = weight_sec(row.get("kinryo"), row.get("age"), di,
                   jockey_rank=jockey_rank, ratio=ratio.early)
    a = age_sec(row.get("age"), row["date"], di)

    # 区間に割って戻す。上がりが取れない馬は全体を平均比で戻す。
    if ag and bl:
        adj_e = (t - ag) / ratio.early - w * KIN_SPLIT_EARLY
        adj_l = ag / ratio.late - w * (1 - KIN_SPLIT_EARLY)
    else:
        adj_e, adj_l = t / ((ratio.early + ratio.late) / 2) - w, 0.0
    adj = adj_e + adj_l

    gap = bw - adj + a
    bt = CENTER + gap / dist_coef(di) * 10.0
    parts = {"斤量": round(w, 2), "年齢": round(a, 2), "馬場": 0.0, "ペース": 0.0}

    # ── ペース補正ブレンド ──────────────────────────────────
    d = pace_dev(row, bw, bl) if (pace and ag and bl) else None
    if d is not None and abs(d) > BLEND_DEAD:
        bw_e, bw_l = bw - bl, bl
        share = max(di - 600, 200)
        if d < 0:
            # ハイペース: 前半でどれだけ脚を使ったかで測り直す。
            # 追い込み馬は前半が遅い→下方修正、先行して粘った馬は上方修正。
            sec = CENTER + (bw_e - adj_e + a * share / di) / dist_coef(share) * 10.0
        else:
            # スローペース: 全体が遅くなるので、上がりで測り直して底上げする。
            sec = CENTER + (bw_l - adj_l + a * 600 / di) / dist_coef(600) * 10.0
        k = min(BLEND_MAX, BLEND_K * (abs(d) - BLEND_DEAD))
        before = bt
        bt = (1 - k) * bt + k * sec
        parts["ペース"] = round(bt - before, 2)

    # ── 馬場状態補正（最終段）────────────────────────────────
    if baba:
        adj_b = BABA_ADJ.get(norm_baba(row.get("baba")) or "良", 0.0)
        bt += adj_b
        parts["馬場"] = adj_b

    return BTResult(bt=round(bt, 1), base=bw, adjusted=round(adj, 2),
                    gap=round(gap, 2), level=level, ratio=ratio, parts=parts)
