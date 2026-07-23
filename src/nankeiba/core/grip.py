"""グリップ血統（中山×道悪）タグ。

仮説（note/funkkeiba 血統考察 ＋ 当システムの実測観察）:
  「中山の急坂を苦にしないパワー・コーナリング」×「重/不良を苦にしないグリップ」を
  併せ持つ血 → 夏のNARダート（散水で湿ってタフ化する白砂）で人気薄でも激走する。

対象は**サンデー系の中山/道悪巧者サブグループ**と**ロベルト系（ターントゥ）**が中心。
大系統（pedigree.py）より一段細かいキュレーションで、産駒（父or母父）を拾う。

⚠️ 効果は未確認。30日検証(2026-07)では夏ダート全体で複勝28.7% vs 非該当27.9%＝
   エッジ+0.8%とほぼ消失（人気8＋は9.7%でbaseline以下）。記事の「人気薄で激走」は
   この検証では支持されなかった。ただし記事は「湿った白砂」限定の主張で、道悪日に
   絞った再検証は未実施。→ 穴フラグとしては未採用。馬場フィルタ再測定が次の課題。
依存ライブラリなし。
"""

from __future__ import annotations

from dataclasses import dataclass

from .pedigree import _normalize

# 中山×道悪グリップ 種牡馬（父/母父で拾う）。記事の6頭＋同筋の中山巧者を核に。
GRIP_SIRES_RAW = [
    # --- サンデー系サブ（中山巧者・道悪巧者） ---
    "フジキセキ", "キンシャサノキセキ", "ネオユニヴァース", "ゴールドアリュール",
    "コパノリッキー",            # ゴールドアリュール系ダートパワー
    "ヴィクトワールピサ",        # 父ネオユニ・中山GI2勝(皐月賞/有馬)＋ドバイWC＝中山×道悪の体現
    # --- ロベルト系（ターントゥ／パワー・グリップ） ---
    "エピファネイア", "シンボリクリスエス", "ブライアンズタイム", "タニノギムレット",
    "スクリーンヒーロー", "モーリス", "ロージズインメイ",
    # --- 記事に挙がった現役馬（種牡馬入り＝母父で拾う可能性） ---
    "ニシケンモノノフ", "アルアイン",
]

GRIP_SIRES = {_normalize(s) for s in GRIP_SIRES_RAW}


def is_grip(name: str | None) -> bool:
    """種牡馬名がグリップ血統リストに該当するか（部分一致）。"""
    n = _normalize(name)
    if not n:
        return False
    if n in GRIP_SIRES:
        return True
    return any(g in n or n in g for g in GRIP_SIRES)


@dataclass
class GripTag:
    sire: bool          # 父がグリップ
    bms: bool           # 母父がグリップ

    def __bool__(self) -> bool:
        return self.sire or self.bms

    @property
    def mark(self) -> str:
        if self.sire and self.bms:
            return "🔩父母"
        if self.sire:
            return "🔩父"
        if self.bms:
            return "🔩母父"
        return ""


def grip_of(sire: str | None, bms: str | None) -> GripTag:
    return GripTag(sire=is_grip(sire), bms=is_grip(bms))
