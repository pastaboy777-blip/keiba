"""属性スプリット集計器（穴ぐさの [x.x.x.x] 裏付けデータを移植）。

穴ぐさは推奨の裏付けに **属性×条件の成績スプリット** を必ず添える:
  「モーリス牝馬は新潟芝1400ｍで4〜8枠だと[6.4.1.21]（複勝率34.4％）」
  「M.デムーロ騎手は中京芝1600mが[19.15.16.62]（複勝率44.6％）」
主語の内訳（実測92件）＝ 絞込条件48 / **産駒(父)30 / 騎手16 / 厩舎13** / 母父配合1。
＝ **父×コース×枠** と **騎手×コース** が二枚看板。

ここでは任意の「結果レコード列」を、任意のキー関数でグルーピングして
[勝.連対増.3着.着外] = [win, place, show, out] の成績（＝JRA式[x.x.x.x]）と
複勝率を出す汎用エンジンを実装する。父・騎手・厩舎いずれのスプリットも同じ器で作れる。

⚠️ 正直な注意（rule4）: 後方視で絞ったスプリットは軸選択でいくらでも良く見せられる
   （チェリーピック）。最小サンプル(min_n)と複勝率の両方を見て、単体では買わない。
依存ライブラリなし。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence


@dataclass(frozen=True)
class Outcome:
    """1走の結果（スプリット集計の最小単位）。属性は任意のdictで持つ。"""

    finish_pos: int
    attrs: dict           # 例 {'sire':'モーリス','place':'新潟','surface':'芝','distance':1400,'waku':7,'sex':'牝'}


@dataclass(frozen=True)
class Record:
    """[x.x.x.x] 成績レコード。"""

    win: int              # 1着
    place: int            # 2着
    show: int             # 3着
    out: int              # 着外

    @property
    def n(self) -> int:
        return self.win + self.place + self.show + self.out

    @property
    def top3(self) -> int:
        return self.win + self.place + self.show

    @property
    def fukusho(self) -> float:
        return self.top3 / self.n if self.n else 0.0

    @property
    def win_rate(self) -> float:
        return self.win / self.n if self.n else 0.0

    def bracket(self) -> str:
        return f"[{self.win}.{self.place}.{self.show}.{self.out}]"

    def describe(self) -> str:
        return f"{self.bracket()}（複勝率{self.fukusho*100:.1f}％）"


def tally(outcomes: Iterable[Outcome]) -> Record:
    """結果列を [win.place.show.out] に集計。"""
    w = p = s = o = 0
    for oc in outcomes:
        fp = oc.finish_pos
        if fp == 1:
            w += 1
        elif fp == 2:
            p += 1
        elif fp == 3:
            s += 1
        else:
            o += 1
    return Record(w, p, s, o)


def split(
    outcomes: Sequence[Outcome],
    keyfn: Callable[[Outcome], object],
    *,
    min_n: int = 1,
) -> dict[object, Record]:
    """keyfn でグルーピングして {キー: Record} を返す（min_n未満のキーは除外）。"""
    groups: dict[object, list[Outcome]] = {}
    for oc in outcomes:
        k = keyfn(oc)
        if k is None:
            continue
        groups.setdefault(k, []).append(oc)
    out: dict[object, Record] = {}
    for k, ocs in groups.items():
        if len(ocs) >= min_n:
            out[k] = tally(ocs)
    return out


def filtered(
    outcomes: Sequence[Outcome],
    where: dict,
) -> list[Outcome]:
    """attrs が where の全条件に一致する結果だけ抜く。

    where の値が (a, b) タプルなら範囲 a<=x<=b、list/set なら含有、それ以外は等値。
    例 where={'sire':'モーリス','surface':'芝','distance':1400,'waku':(4,8)}
    """
    def ok(oc: Outcome) -> bool:
        for k, cond in where.items():
            v = oc.attrs.get(k)
            if v is None:
                return False
            if isinstance(cond, tuple) and len(cond) == 2:
                if not (cond[0] <= v <= cond[1]):
                    return False
            elif isinstance(cond, (list, set)):
                if v not in cond:
                    return False
            else:
                if v != cond:
                    return False
        return True

    return [oc for oc in outcomes if ok(oc)]


def cross_stat(
    outcomes: Sequence[Outcome],
    where: dict,
) -> Record:
    """穴ぐさ流『○○は△△だと[x.x.x.x]』を1発で: where で絞って集計。"""
    return tally(filtered(outcomes, where))


# --- スプリット・テーブル（事前集計を引くだけの軽量ルックアップ） ---

@dataclass
class SplitTable:
    """{主語: {条件キー: Record}} の事前集計ルックアップ。

    父×コース×枠、騎手×コース などを一度作って保存し、予想時に引く用途。
    """

    table: dict[str, dict[str, Record]]

    def lookup(self, subject: str, cond_key: str) -> Record | None:
        return self.table.get(subject, {}).get(cond_key)

    def to_json(self) -> dict:
        return {
            subj: {ck: [r.win, r.place, r.show, r.out] for ck, r in d.items()}
            for subj, d in self.table.items()
        }

    @classmethod
    def from_json(cls, data: dict) -> "SplitTable":
        table = {
            subj: {ck: Record(*vals) for ck, vals in d.items()}
            for subj, d in data.items()
        }
        return cls(table=table)

    @classmethod
    def build(
        cls,
        outcomes: Sequence[Outcome],
        subject_fn: Callable[[Outcome], str | None],
        cond_fn: Callable[[Outcome], str | None],
        *,
        min_n: int = 3,
    ) -> "SplitTable":
        """結果列から (主語, 条件) 別スプリットを構築。"""
        groups: dict[str, dict[str, list[Outcome]]] = {}
        for oc in outcomes:
            subj = subject_fn(oc)
            ck = cond_fn(oc)
            if subj is None or ck is None:
                continue
            groups.setdefault(subj, {}).setdefault(ck, []).append(oc)
        table: dict[str, dict[str, Record]] = {}
        for subj, conds in groups.items():
            for ck, ocs in conds.items():
                if len(ocs) >= min_n:
                    table.setdefault(subj, {})[ck] = tally(ocs)
        return cls(table=table)
