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

⚠️⚠️ **南関では作れない補正がある。**
   * **馬ごとのテン3F が存在しない。** 公開されているハロンラップは**先頭の**もの。
     各馬について取れるのは「走破タイム」と「上がり3F」だけなので、前半は
     `走破タイム − 上がり3F` としてしか出せない。仕様のペース補正ブレンドが
     要求する「その馬のテン3F」は**近似すらできない**（通過順からの推定は可能だが
     時計ではない）。Phase 3 はここを正面から扱う必要がある。
   * **不利データが無い。** 南関の結果ページには「出遅れ」「不利」の記載が
     1件も無い（実測）。仕様の不利補正3層のうち第2層・第3層は**南関では不可**。
     中央（競馬ブック「発走状況他」）には有るので、そちらでは作れる。

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

⚠️ **ペース補正が無い影響は大きい。**3着内馬のBT値の中央値:

       速い上がりのレース（瞬発戦）  57.3
       標準                        52.5
       遅い上がりのレース（消耗戦）  47.1     ← 10.2ポイント差

   脚質でも 前53.2 / 中51.1 / 後50.4 と前が2.8ポイント高い。
   この差が「本当に強いレースだった」のか「展開の恩恵を能力と誤認している」
   のかを、**いまの実装は分離できない**。仕様のペース補正ブレンドは
   まさにそこを分ける装置なので、Phase 3 の優先度が一番高い。

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
#: 一律57kg基準にすると牝馬の2kg減が補正に乗らない、というのが仕様の指摘。
#: 2歳だけは牡も牝も54.0で差が無い（南関では2歳に牝馬減量が無い）。
STD_KINRYO = {"2": 54.0, "3": 56.0, "old": 56.0}
#: 1kgあたりの秒数（ダート・1600m基準）。⚠️ 未測定の初期値。
SEC_PER_KG = 0.16
#: 距離ごとの効き。短距離ほど大きい（仕様どおり）。アンカー間は線形補間。
_DIST_ANCHOR = ((800, 1.30), (1200, 1.15), (1600, 1.00), (2000, 0.92), (2600, 0.78))
#: 騎手ランク（1=リーディング上位…5=見習い）ごとの倍率。⚠️ 未測定の初期値。
JOCKEY_MULT = {1: 0.80, 2: 0.90, 3: 1.00, 4: 1.10, 5: 1.20}
#: 高速馬場での二次補正の強さ。馬場比が1.0を下回るほど斤量差が効く（仕様）。
FAST_TRACK_K = 1.5


def dist_mult(distance: int) -> float:
    """距離連続関数。アンカー間を線形補間する。"""
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
    """
    if not kinryo:
        return 0.0
    d = kinryo - STD_KINRYO[age_group(age)]
    k = SEC_PER_KG * dist_mult(distance) * JOCKEY_MULT.get(jockey_rank, 1.0)
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


@dataclass
class BTResult:
    bt: float
    base: float
    adjusted: float
    gap: float
    level: str
    ratio: TrackRatio
    parts: dict


def score(row: dict, base: BaseTime, ratio: TrackRatio,
          *, jockey_rank: int = 3) -> BTResult | None:
    """1頭の1走を BT値にする。基準タイムが引けなければ None。"""
    t = row.get("time_sec")
    if not t:
        return None
    bw, bl, level = base.unified(row["place"], row["distance"])
    if not bw:
        return None
    ag = row.get("agari")
    # 馬場比で戻す。上がりが取れない馬は全体を前半比だけで戻す（精度は落ちる）。
    if ag and bl:
        adj = (t - ag) / ratio.early + ag / ratio.late
    else:
        adj = t / ((ratio.early + ratio.late) / 2)
    w = weight_sec(row.get("kinryo"), row.get("age"), row["distance"],
                   jockey_rank=jockey_rank, ratio=ratio.early)
    adj -= w
    a = age_sec(row.get("age"), row["date"], row["distance"])
    gap = bw - adj + a
    bt = CENTER + gap / dist_coef(row["distance"]) * 10.0
    return BTResult(bt=round(bt, 1), base=bw, adjusted=round(adj, 2),
                    gap=round(gap, 2), level=level, ratio=ratio,
                    parts={"斤量": round(w, 2), "年齢": round(a, 2)})
