"""クロス濃縮スコア（穴ぐさのインブリード活用を移植）。

穴ぐさはクロス（インブリード）を **「適性の濃縮タグ」** として使う（年間1.4%＝スパイス）:
  ・近い代（4×3, 5×4 など4〜5代以内）のクロスだけ見る。
  ・祖先を"適性"に変換する（ストームキャット/デピュティミニスター＝ダート道悪パワー、
    ダンチヒ／デインヒル＝スピード短距離、サドラーズ／ニジンスキー＝スタミナ）。
  ・**「強い」根拠ではなく"今日の馬場・距離に合う理由"** として、必ず条件とセットで使う。

ここでは 5代血統表（祖先の出現＝父方/母方×代数）から:
  1. 父方・母方の両側に4〜5代以内で現れる祖先＝クロスを検出。
  2. その祖先の適性タグ（DIRT_POWER / SPEED / STAMINA / TURF_KIRE）を集計。
  3. 今日の条件（馬場・芝ダ・距離）と一致するタグに濃縮ボーナスを付ける。

⚠️ 正直な注意（rule4）: クロス効果はエビデンスが弱い（穴ぐさもクロスには[x.x.x.x]の
   裏付けを付けない＝"語り"）。特に新馬・データ薄の馬の適性代替推定に向く道具で、
   **採用は out-of-sample の複勝回収を測ってから**。5代血統表が要る（楽天は父/母父まで、
   netkeiba の血統頁に5代がある）。依存ライブラリなし。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .pedigree import _normalize

# --- 適性タグ ---
DIRT_POWER = "DIRT_POWER"    # ダート・道悪・パワー・持続
SPEED = "SPEED"              # スピード・短距離
STAMINA = "STAMINA"          # スタミナ・長距離
TURF_KIRE = "TURF_KIRE"      # 芝の瞬発・キレ

# 祖先 → 適性タグ（穴ぐさが実際にクロスで使った祖先＋同系の定番を核に）。
# ⚠️ netkeiba 5代表は gen3以降が外国馬＝英語表記で返る（"Storm Cat""Halo"）。
#    カタカナと英語(小文字化・記号除去で正規化)の両方を登録する。
_ANCESTOR_TAGS_RAW: dict[str, set[str]] = {
    # ダート・道悪・パワー系
    "ストームキャット": {DIRT_POWER, SPEED}, "Storm Cat": {DIRT_POWER, SPEED},
    "ストームバード": {DIRT_POWER}, "Storm Bird": {DIRT_POWER},
    "デピュティミニスター": {DIRT_POWER}, "Deputy Minister": {DIRT_POWER},
    "フレンチデピュティ": {DIRT_POWER}, "French Deputy": {DIRT_POWER},
    "クロフネ": {DIRT_POWER},
    "ロベルト": {DIRT_POWER, STAMINA}, "Roberto": {DIRT_POWER, STAMINA},
    "ブライアンズタイム": {DIRT_POWER},
    "シンボリクリスエス": {DIRT_POWER},
    "エーピーインディ": {DIRT_POWER}, "A.P. Indy": {DIRT_POWER}, "AP Indy": {DIRT_POWER},
    "ミスタープロスペクター": {DIRT_POWER, SPEED}, "Mr. Prospector": {DIRT_POWER, SPEED},
    "フォーティナイナー": {DIRT_POWER, SPEED}, "Forty Niner": {DIRT_POWER, SPEED},
    "ノーザンテースト": {DIRT_POWER, STAMINA}, "Northern Taste": {DIRT_POWER, STAMINA},
    # スピード・短距離系
    "ダンチヒ": {SPEED}, "Danzig": {SPEED},
    "デインヒル": {SPEED}, "Danehill": {SPEED},
    "サクラバクシンオー": {SPEED},
    "ヘイルトゥリーズン": {SPEED}, "Hail to Reason": {SPEED},
    "ノーザンダンサー": {SPEED, STAMINA}, "Northern Dancer": {SPEED, STAMINA},  # 万能・パワー
    # スタミナ・長距離系
    "サドラーズウェルズ": {STAMINA, DIRT_POWER}, "Sadler's Wells": {STAMINA, DIRT_POWER},
    "ニジンスキー": {STAMINA}, "Nijinsky": {STAMINA},
    "トニービン": {STAMINA}, "Tony Bin": {STAMINA},
    "リボー": {STAMINA}, "Ribot": {STAMINA},
    "ミルリーフ": {STAMINA}, "Mill Reef": {STAMINA},
    # 芝キレ系
    "サンデーサイレンス": {TURF_KIRE}, "Sunday Silence": {TURF_KIRE},
    "ヌレイエフ": {TURF_KIRE}, "Nureyev": {TURF_KIRE},
    "リファール": {TURF_KIRE}, "Lyphard": {TURF_KIRE},
    "ダンシングブレーヴ": {TURF_KIRE}, "Dancing Brave": {TURF_KIRE},
    "ヘイロー": {TURF_KIRE, SPEED}, "Halo": {TURF_KIRE, SPEED},
}

ANCESTOR_TAGS = {_normalize(k): v for k, v in _ANCESTOR_TAGS_RAW.items()}


def tags_of(name: str | None) -> set[str]:
    """祖先名の適性タグ集合（不明なら空）。部分一致も許可（『Storm Cat』表記揺れ対策）。"""
    n = _normalize(name)
    if not n:
        return set()
    if n in ANCESTOR_TAGS:
        return set(ANCESTOR_TAGS[n])
    out: set[str] = set()
    for anc, ts in ANCESTOR_TAGS.items():
        if anc in n or n in anc:
            out |= ts
    return out


@dataclass(frozen=True)
class Occurrence:
    """5代血統表内の祖先1出現。gen=代数(1=父/母 … 5)、side='sire'|'dam'。"""

    name: str
    gen: int
    side: str  # 'sire'（父方）/ 'dam'（母方）


@dataclass
class CrossTag:
    ancestor: str
    pattern: str              # 例 '5×4'（父方代×母方代 の代表値）
    closeness: int            # 近さ＝クロスの最小代（小さいほど濃い）
    tags: set[str] = field(default_factory=set)

    def label(self) -> str:
        return f"{self.ancestor}の{self.pattern}"


def detect_crosses(occ: Iterable[Occurrence], *, maxgen: int = 5) -> list[CrossTag]:
    """父方・母方の両側に maxgen 以内で現れる祖先＝クロスを検出する。

    同名祖先の (父方最小代, 母方最小代) を 'm×n'（父方×母方）で表す。
    近い順（closeness昇順）で返す。
    """
    by_name: dict[str, dict[str, list[int]]] = {}
    for o in occ:
        if o.gen > maxgen:
            continue
        key = _normalize(o.name)
        if not key:
            continue
        d = by_name.setdefault(key, {"sire": [], "dam": [], "_disp": o.name})
        d[o.side].append(o.gen)

    out: list[CrossTag] = []
    for key, d in by_name.items():
        sire_gens = d["sire"]
        dam_gens = d["dam"]
        if not sire_gens or not dam_gens:
            continue  # 片側だけ＝クロスではない
        s = min(sire_gens)
        m = min(dam_gens)
        closeness = min(s, m)
        out.append(CrossTag(ancestor=d["_disp"], pattern=f"{s}×{m}",
                            closeness=closeness, tags=tags_of(d["_disp"])))
    out.sort(key=lambda c: (c.closeness, -len(c.tags)))
    return out


# 今日の条件 → 効く適性タグ
def _condition_tags(surface: str | None, baba: str | None,
                    distance: int | None) -> set[str]:
    want: set[str] = set()
    surf = (surface or "")[:1]
    head = (baba or "")[:1]
    dirt = surf == "ダ" or surf == "ダート"[:1]
    heavy = head in ("稍", "重", "不")
    if dirt or heavy:
        want.add(DIRT_POWER)
    if distance is not None:
        if distance <= 1400:
            want.add(SPEED)
        elif distance >= 2200:
            want.add(STAMINA)
    if surf == "芝" and not heavy:
        want.add(TURF_KIRE)
    return want


@dataclass
class CrossScore:
    crosses: list[CrossTag]
    matched: list[CrossTag]       # 今日の条件タグに一致したクロス
    want_tags: set[str]
    score: float                  # 濃縮ボーナス（0〜）

    def label(self) -> str:
        if not self.matched:
            return ""
        best = self.matched[0]
        hit = "・".join(sorted(self.want_tags & best.tags))
        return f"{best.label()}（{hit}濃縮）"


def score(
    occ: Iterable[Occurrence],
    *,
    surface: str | None = None,
    baba: str | None = None,
    distance: int | None = None,
    maxgen: int = 5,
) -> CrossScore:
    """5代血統の出現から、今日の条件に効くクロス濃縮スコアを算出。

    近いクロスほど、かつ条件タグに一致するほど高い。近さ重み = (6 - closeness)/5。
    """
    crosses = detect_crosses(occ, maxgen=maxgen)
    want = _condition_tags(surface, baba, distance)
    matched: list[CrossTag] = []
    total = 0.0
    for c in crosses:
        hit = want & c.tags
        if hit:
            matched.append(c)
            total += (6 - c.closeness) / 5.0 * len(hit)
    matched.sort(key=lambda c: (c.closeness, -len(want & c.tags)))
    return CrossScore(crosses=crosses, matched=matched, want_tags=want,
                      score=round(total, 3))


def occurrences_from_5gen(names_by_gen: dict[int, list[str]]) -> list[Occurrence]:
    """簡易ヘルパ: {代: [その代の祖先名を父方→母方の順で並べたリスト]} から
    Occurrence 列を作る。各代 g には 2**g 頭並び、前半が父方・後半が母方。

    例 gen1=[父, 母], gen2=[父父, 父母, 母父, 母母], … netkeibaの血統表の並びに対応。
    """
    occ: list[Occurrence] = []
    for gen, names in names_by_gen.items():
        half = len(names) // 2 or 1
        for i, nm in enumerate(names):
            if not nm:
                continue
            side = "sire" if i < half else "dam"
            occ.append(Occurrence(name=nm, gen=gen, side=side))
    return occ
