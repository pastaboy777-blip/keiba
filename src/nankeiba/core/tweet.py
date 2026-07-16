"""予測パイプラインの出力を「初速の出る X(旧Twitter)投稿文」に変換する。

X で伸び悩む競馬アカウントの典型パターン(本文リンクで表示が絞られる/
1行目が弱くスクロールで飛ばされる)を避けるため、この生成器は次を守る:

  1. 逆張り本命の抽出   … モデル評価は上位なのに人気が薄い馬(=市場の歪み)を選ぶ
  2. 根拠3点の自動抽出  … 特徴量(間隔・叩き・距離替わり等)から寄与の大きい順に言語化
  3. 断言の1行目       … 「〜かも」を使わず、断言・逆張り・数字で指を止める
  4. 検証予告          … 予告→結果検証をセットにして信用を積む
  5. リンクはリプへ分離 … 外部リンク(netkeiba/note/ツイキャス/LINE)は本文に入れず
                          セルフリプライ側に置く(本文リンクは表示減点の主因)

依存ライブラリなし(標準ライブラリのみ)。`RaceContext`/`RunRecord` は core と共通。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from . import features as ft
from . import interval as iv
from . import probability as pb


# ---------------------------------------------------------------------------
# 入力: 1頭ぶんの出馬表エントリ
# ---------------------------------------------------------------------------

@dataclass
class HorseEntry:
    """出馬表の1頭。過去走 records と今回の人気・単勝を持つ。"""

    um: int                       # 馬番
    name: str                     # 馬名
    win_odds: float               # 単勝オッズ
    popularity: int               # 人気順(1=1番人気)
    records: list[iv.RunRecord]   # 過去走(新しい順)
    jockey: str | None = None     # 今回の騎手(乗り替わり判定に使う)


def entries_from_tuples(rows: Sequence[tuple]) -> list[HorseEntry]:
    """predict_example と同じタプル形式から HorseEntry 列を作るヘルパ。

    行: (um, name, jockey, win_odds, pop,
         [(date, place, dist, field, finish, baba, corner_pos, agari_rank), ...])
    """
    out: list[HorseEntry] = []
    for um, name, jockey, win_odds, pop, runs in rows:
        records = [
            iv.RunRecord(date=d, place=p, distance=dist, field_size=fs,
                         finish_pos=fp, jockey=jockey, baba=b,
                         corner_pos=list(cp), agari_rank=ar)
            for (d, p, dist, fs, fp, b, cp, ar) in runs
        ]
        out.append(HorseEntry(um=um, name=name, win_odds=win_odds,
                              popularity=pop, records=records, jockey=jockey))
    return out


# ---------------------------------------------------------------------------
# 補助: 出走間隔と叩き走目を人が読める言葉に
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> date:
    y, m, d = (int(x) for x in s.split("-"))
    return date(y, m, d)


def interval_phrase(days: int | None) -> str | None:
    """今回の出走間隔[日]を『連闘/中1週…』の口語ラベルにする。"""
    if days is None:
        return None
    if days <= 8:
        return "連闘"
    if days <= 15:
        return "中1週"
    if days <= 22:
        return "中2週"
    if days <= 35:
        return "中3〜4週"
    if days <= 60:
        return "間隔開け"
    return "休み明け"


def _upcoming_days(entry: HorseEntry, race_date: str) -> int | None:
    if not entry.records:
        return None
    return (_parse_date(race_date) - _parse_date(entry.records[0].date)).days


# ---------------------------------------------------------------------------
# 根拠3点: 特徴量の寄与(重み×値)が大きい順に言語化する
# ---------------------------------------------------------------------------

def _reason_texts(
    entry: HorseEntry,
    ctx: ft.RaceContext,
    weights: ft.ScoreWeights,
) -> list[str]:
    """この馬の『市場が見落としている根拠』を寄与の大きい順に返す。"""
    feats = ft.horse_features(entry.records, ctx)
    w = weights.as_dict()
    days = _upcoming_days(entry, ctx.date)
    n_tatakii = ft.starts_since_layoff(entry.records, days)
    ph = interval_phrase(days)

    # (特徴量キー, 寄与=重み×値, 口語テキスト) の候補。寄与>0 のものだけ採用。
    cand: list[tuple[str, float, str]] = []

    def add(key: str, text: str) -> None:
        contrib = w.get(key, 0.0) * feats.get(key, 0.0)
        if contrib > 1e-6:
            cand.append((key, contrib, text))

    if ph in ("連闘", "中1週"):
        add("interval_fit", f"{ph}=南関で最も動く詰め間隔なのに人気薄")
    elif ph is not None:
        add("interval_fit", f"{ph}がこの馬に合う間隔")
    if n_tatakii in (2, 3):
        add("tatakii", f"叩き{n_tatakii}走目=上昇力のピーク")
    add("distance_fit", f"今回のダ{ctx.distance}mは自身の好走圏")
    if ctx.place:
        add("place_fit", f"{ctx.place}替わり/{ctx.place}巧者で舞台が合う")
    add("senkou", "先行力あり=小回り南関で前が止まらない")
    add("agari", "末脚上位=展開が向けば差し込める")
    if ctx.baba:
        add("baba_fit", f"{ctx.baba}馬場が得意")
    add("toughness", "タフな体質=詰めても崩れない")
    add("jockey_change", "上位騎手への強化乗り替わり")

    cand.sort(key=lambda t: t[1], reverse=True)
    texts = [t[2] for t in cand[:3]]

    # 3点に満たなければ地力で埋める(逆張りの説得力を最低限確保)
    if len(texts) < 3 and feats.get("ability", 0.0) > 0:
        texts.append("地力は足りている(着順ベースで上位)")
    return texts[:3]


# ---------------------------------------------------------------------------
# 出力: ツイート下書き
# ---------------------------------------------------------------------------

@dataclass
class TweetDraft:
    style: str                 # 'gyakubari' / 'iwakan' / 'suuji'
    body: str                  # 本文(リンクを含めない)
    replies: list[str] = field(default_factory=list)  # セルフリプライ(根拠・リンク)

    @property
    def weighted_len(self) -> int:
        return tweet_weighted_len(self.body)

    @property
    def over_limit(self) -> bool:
        return self.weighted_len > 280

    def render(self) -> str:
        lines = [self.body]
        for i, r in enumerate(self.replies, 1):
            lines.append(f"\n  └─ リプ{i} ──────────\n{r}")
        return "\n".join(lines)


@dataclass
class TweetPlan:
    honmei: HorseEntry
    partners: list[HorseEntry]
    reasons: list[str]
    favorite_downgraded: bool
    drafts: list[TweetDraft]


def tweet_weighted_len(s: str) -> int:
    """X の文字数カウント近似(CJK など全角は2、半角は1)。"""
    n = 0
    for ch in s:
        n += 1 if ord(ch) < 0x1100 else 2
    return n


# ---------------------------------------------------------------------------
# 本命(逆張り)の選定
# ---------------------------------------------------------------------------

def _rank(
    entries: Sequence[HorseEntry],
    ctx: ft.RaceContext,
    weights: ft.ScoreWeights,
) -> list[HorseEntry]:
    """モデルスコアの高い順に並べ替える。"""
    def score(e: HorseEntry) -> float:
        e_ctx = ft.RaceContext(date=ctx.date, place=ctx.place, distance=ctx.distance,
                               field_size=ctx.field_size, jockey=e.jockey, baba=ctx.baba)
        return ft.horse_score(e.records, e_ctx, weights=weights)
    return sorted(entries, key=score, reverse=True)


def select_honmei(
    entries: Sequence[HorseEntry],
    ctx: ft.RaceContext,
    weights: ft.ScoreWeights,
    *,
    top_k: int = 5,
    min_pop: int = 4,
) -> tuple[HorseEntry, list[HorseEntry], bool]:
    """逆張り本命(モデル上位×人気薄)と相手、1番人気の格下げ有無を返す。

    モデル上位 top_k の中で最も人気の無い(pop が大きい)馬を本命にする。
    ただし人気薄が居なければモデル1位を本命にする(素直な本線)。
    """
    order = _rank(entries, ctx, weights)
    head = order[:top_k]
    # モデル上位のうち min_pop 以上に人気薄な馬 → 最も人気の無いものを本命に
    dark = [e for e in head if e.popularity >= min_pop]
    honmei = max(dark, key=lambda e: e.popularity) if dark else order[0]
    partners = [e for e in order[:4] if e.um != honmei.um][:3]

    # 1番人気がモデルで4番手以下なら「格下げ」= 逆張りの旗を立てられる
    fav = min(entries, key=lambda e: e.popularity)
    fav_rank = order.index(fav) + 1
    favorite_downgraded = fav_rank >= 4 and fav.um != honmei.um
    return honmei, partners, favorite_downgraded


# ---------------------------------------------------------------------------
# 生成本体
# ---------------------------------------------------------------------------

def generate(
    entries: Sequence[HorseEntry],
    ctx: ft.RaceContext,
    *,
    weights: ft.ScoreWeights | None = None,
    race_label: str = "",
    link: str | None = None,
    roi_pct: float | None = None,
) -> TweetPlan:
    """出馬表とレース条件から、初速の出るツイート下書き一式を生成する。"""
    weights = weights or ft.ScoreWeights()

    honmei, partners, fav_down = select_honmei(entries, ctx, weights)
    h_ctx = ft.RaceContext(date=ctx.date, place=ctx.place, distance=ctx.distance,
                           field_size=ctx.field_size, jockey=honmei.jockey, baba=ctx.baba)
    reasons = _reason_texts(honmei, h_ctx, weights)

    base = f"{ctx.place}{race_label}".strip()
    pop = honmei.popularity
    teaser = reasons[0] if reasons else "市場が見落としている条件がある"

    # 根拠リプ(セルフリプライ1) と リンクリプ(セルフリプライ2)
    reason_block = (
        f"なぜ人気薄の{honmei.name}か。市場が見てない点👇\n"
        + "\n".join(f"・{r}" for r in reasons)
        + "\n\n派手な人気より、地味な間隔と叩き。南関はこれが回収率。"
    )
    replies_common: list[str] = [reason_block]
    if link:
        replies_common.append(f"予想の続き・実況はこちら👇\n{link}")

    drafts: list[TweetDraft] = []

    # ── A. 逆張り断言(予告)── 最も初速が出る本命フォーマット
    if fav_down:
        hook = f"{base}、1番人気は軸にしません。"
    elif pop >= 4:
        hook = f"{base}、狙うのは{pop}番人気。"
    else:
        hook = f"{base}、本命の根拠を先に出します。"
    body_a = (
        f"{hook}\n\n"
        f"本命 ◎{honmei.um} {honmei.name}({pop}番人気)\n"
        f"{teaser}\n\n"
        f"発走前に晒します。結果は後で必ず検証します。"
    )
    drafts.append(TweetDraft("gyakubari", body_a, list(replies_common)))

    # ── C. 違和感・問いかけ(リプ誘発)── 根拠を本文に載せる変種
    reason_lines = "\n".join(f"・{r}" for r in reasons)
    body_c = (
        f"この馬、なんで{pop}番人気なんですか?\n\n"
        f"{reason_lines}\n\n"
        f"{base}、本命はコイツ。◎{honmei.um} {honmei.name}"
    )
    drafts.append(TweetDraft("iwakan", body_c, [r for r in replies_common if link and r.startswith("予想")]))

    # ── B. 数字フック(回収率がある時のみ)── 信用を積む
    if roi_pct is not None:
        body_b = (
            f"南関の三連複、直近の回収率 {roi_pct:.0f}%。\n\n"
            f"的中率は高くない。でも「人気を買わない」から負けにくい。\n\n"
            f"今日の本命も{pop}番人気。◎{honmei.um} {honmei.name}。理由は下に。"
        )
        drafts.append(TweetDraft("suuji", body_b, list(replies_common)))

    return TweetPlan(
        honmei=honmei,
        partners=partners,
        reasons=reasons,
        favorite_downgraded=fav_down,
        drafts=drafts,
    )


STYLE_LABEL = {
    "gyakubari": "A. 逆張り断言(予告)",
    "iwakan": "C. 違和感・問いかけ",
    "suuji": "B. 数字フック",
}
