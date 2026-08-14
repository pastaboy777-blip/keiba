"""きついラップを走った組 ── レースを起点に、走った馬をまとめて追う。

ユーザー提示（2026-08-14）の考え方をそのまま道具にしたもの。

    前開催の全レースから「**11秒台が3本以上 かつ 最遅−最速が1.5秒以内**」の
    レースを抜き出す。そこに出走していた馬を**全頭**リストにして、次の開催で
    出てくるところを追う。

**指数ではない。**個々の馬を点数化するのではなく、**レースを単位に集団を追う**。
緩まないラップを最後まで走らされた経験が、次に時計のかかる馬場で出る、という読み。

── 定義（提示された数字から逆算し、3レースで一致を確認）──────────

    11秒台の本数 … ハロンラップのうち 12.0秒未満の本数。**3本以上**
    最速差       … **最遅ハロン − 最速ハロン**。**1.5秒以内**

        7/21 大井9R  12.4 11.5 11.8 12.5 11.9 12.7 → 3本 / 1.2 ✓
        7/21 大井7R  12.7 11.5 11.9 12.6 11.8 12.9 → 3本 / 1.4 ✓
        7/20 大井11R 13.0 11.5 11.5 11.8 12.3 11.8 13.0 → 4本 / 1.5 ✓

⚠️ **半端な先頭ハロンを混ぜないこと。**1300m・1500m などは最初が 6.7 や 7.1 の
   部分ハロンで始まる。これを最速として拾うと最速差が常に5秒以上になり、
   **その距離が丸ごと候補から消える**。10秒未満は落とす。

── 実測（この考え方を目の前の開催で確かめた結果）───────────────

⚠️⚠️ **1回目は当たり、2回目は外れた。正直に両方記録する。**

    2026-08-12 大井8R … 1・2・3着が**全部** 7/21 9R組。6頭出走で4頭が3着内
                        （12・7・5・10番人気）。複勝6点600円 → 6,970円。
    2026-08-14 大井   … 同じ抽出で13頭を追跡。**3着内は2頭（15%）**。
                        本命とされた5R（この組6頭）は
                        ①チェイスザファイア 9人気2着 の1頭だけ。
                        他は 4・7・8・13・14着。
                        7R ⑥サッキーミツグ 5人気1着 が拾えたのが2頭目。

    12〜16頭立てで3着内は素で20%前後なので、**15%はむしろ下**。
    ただし n=13。**この2日で結論を出さないこと。**

⚠️ 恒久ルール5により、過去開催をまとめた勝率・回収率の集計はしていない。
   確かめるなら**目の前の開催**で、当たり外れをそのまま記録すること。
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: 11秒台とみなす上限[秒]。
SUB12 = 12.0
#: 部分ハロン（半端な先頭区間）とみなす下限[秒]。これ未満は計算から外す。
PARTIAL = 10.0
#: 既定のしきい値。
MIN_SUB12 = 3
MAX_SPREAD = 1.5


@dataclass
class LapShape:
    """1レースのラップの形。"""

    laps: list = field(default_factory=list)
    sub12: int = 0
    spread: float | None = None
    ten3f: float | None = None

    @property
    def kitsui(self) -> bool:
        return bool(self.spread is not None
                    and self.sub12 >= MIN_SUB12 and self.spread <= MAX_SPREAD)

    def line(self) -> str:
        return (f"11秒台{self.sub12}本／最速差{self.spread:+.1f}"
                if self.spread is not None else "ラップなし")


def shape(laps, *, min_sub12: int = MIN_SUB12,
          max_spread: float = MAX_SPREAD) -> LapShape:
    """ハロンラップから形を測る。

    ⚠️ **部分ハロンを外してから min/max を取る。**外さないと 1500m のような
       半端距離が「最速差5秒以上」になって全部落ちる。
    """
    full = [x for x in (laps or []) if x >= PARTIAL]
    if len(full) < 4:
        return LapShape(laps=list(laps or []))
    sub = sum(1 for x in full if x < SUB12)
    sp = round(max(full) - min(full), 2)
    t3 = round(sum((laps or [])[:3]), 1) if len(laps or []) >= 3 else None
    s = LapShape(laps=list(laps), sub12=sub, spread=sp, ten3f=t3)
    # しきい値を差し替えられるように、判定はここでも持つ
    s.kitsui_custom = (sub >= min_sub12 and sp <= max_spread)   # type: ignore[attr-defined]
    return s


@dataclass
class KitsuiRace:
    """きついラップだったレースと、そこを走った馬。"""

    date: str
    place: str
    race_no: int | None
    distance: int
    field_size: int
    shape: LapShape
    runners: list = field(default_factory=list)   # [{name,finish,popularity,corner4}]

    def label(self) -> str:
        return (f"{self.date} {self.place}{self.race_no or '?'}R "
                f"{self.distance}m {self.field_size}頭　{self.shape.line()}")


def collect(rows, *, min_sub12: int = MIN_SUB12,
            max_spread: float = MAX_SPREAD) -> list:
    """`bt_extract` 形式の1頭1行レコードから、きついラップのレースを抜き出す。

    `rows` は同じレースの馬が `rid` でまとまっている前提。
    """
    by: dict = {}
    for r in rows:
        by.setdefault(r["rid"], []).append(r)
    out = []
    for rid, rs in by.items():
        h = rs[0]
        sh = shape(h.get("laps"), min_sub12=min_sub12, max_spread=max_spread)
        if not getattr(sh, "kitsui_custom", sh.kitsui):
            continue
        out.append(KitsuiRace(
            date=h["date"], place=h["place"], race_no=h.get("race_no"),
            distance=h["distance"], field_size=len(rs), shape=sh,
            runners=sorted(
                [{"name": x["name"], "finish": x.get("finish"),
                  "popularity": x.get("popularity"), "corner4": x.get("corner4"),
                  "time_sec": x.get("time_sec")} for x in rs],
                key=lambda x: x["finish"] or 99)))
    out.sort(key=lambda r: (r.date, r.race_no or 0))
    return out


def chase(races, entries_by_race: dict) -> dict:
    """追跡。`entries_by_race` は `{レース番号: [馬名, ...]}`（追う日の出馬表）。

    return: `{レース番号: [(馬名, 出典の KitsuiRace, その時の着順/人気), ...]}`

    ⚠️ **同名馬の取り違えに注意。**南関は同名がまず無いが、名寄せは名前だけで
       やっている。将来 horseid で突合するほうが安全。
    """
    src: dict = {}
    for kr in races:
        for x in kr.runners:
            src.setdefault(x["name"], []).append((kr, x))
    out: dict = {}
    for rno, names in entries_by_race.items():
        got = []
        for nm in names:
            if nm in src:
                kr, x = src[nm][0]
                got.append((nm, kr, x))
        if got:
            out[rno] = got
    return out
