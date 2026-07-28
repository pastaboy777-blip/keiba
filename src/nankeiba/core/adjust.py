"""指数の補正項 — 斤量・位置取りロス・出遅れ（JRDB IDM の「記憶要素」の簡易版）。

うちの Engine B は `10 × (par + 当日馬場差 − 走破タイム)` で、
**西田式にもJRDB IDMにも入っている斤量補正が抜けていた**。ここで足す。
併せて IDM の「記憶要素」（出遅・不利・位置取り）のうち、
**楽天の馬柱から復元できるぶんだけ**を近似する。

⚠️ 何が測れて何が測れないか（正直に）:
  測れる … 斤量 / 通過順から推定する外回りロス / 自分の平均より極端に後ろの立ち上がり
  測れない … 実際の進路取り、不利の有無、砂被り。映像を見ないと分からない。
  したがってこれは IDM の代用ではなく、**IDMが人手で入れている情報の一部を
  機械的に近似したもの**にすぎない。効果は必ず実測で確かめること。
  実際、**斤量補正も位置取りの足し戻しも、実測して両方とも棄却した**。
  生き残ったのは `revenge()`（前走大敗×前々のポジション）だけ。

⚠️ 斤量の係数を素の回帰で求めてはいけない。**強い馬ほど重い斤量を背負う**ので、
レース内の斤量差とタイム差の素の相関は「重いほど速い」という**逆符号**になる
（実測 -0.0140 s/F・8,534レース）。同じ馬の中での斤量の増減＝馬内変動だけを使う。

実測の結論（南関キャッシュ 8,534レース / 93,724頭走、2026-07-28）:
  馬内変動での斤量の効果は **+0.0003 s/F/kg ＝ 実質ゼロ**。
  1400m で 1kg = 0.002秒 = 指数 0.02pt。指数は1レースで±50pt動くのでノイズ。
  ・そもそも南関の平場は斤量が動かない（54%が中央値と同斤量）。
  ・さらに **軽い斤量はほぼ見習騎手**だった:
        -3kg → 見習率 **95.7%** ／ -1kg → 47.4% ／ ±0 → 2.9% ／ +2kg → 0.1%
    軽量の物理的な有利さが騎乗の差で相殺され、正味ゼロに見える。
  → よって `SEC_PER_KG_PER_F = 0.0`（＝補正しない）を既定にする。
    式そのものは残してあるので、中央やハンデ戦に広げるときは係数を差し替える。

依存ライブラリなし。
"""

from __future__ import annotations

from dataclasses import dataclass

from .interval import RunRecord

#: 斤量1kgあたりの遅れ [s/F]。`scripts/measure_adjust.py` の馬内変動推定で求める。
#: 正 = 重いほど遅い。
SEC_PER_KG_PER_F = 0.0
#: 基準斤量[kg]。これとの差で補正する。
BASE_KINRYO = 55.0

#: 外を回った1頭ぶんの余分な距離[m]（コーナー半径から見た概算）。
#: 4角で内から n 頭ぶん外にいると、1コーナーあたり約 n×この値だけ余計に走る。
WIDE_M_PER_HORSE = 3.0


# ---------------------------------------------------------------------------
# 斤量
# ---------------------------------------------------------------------------

def kinryo_sec(kinryo: float | None, distance: int | None,
               *, sec_per_kg_per_f: float | None = None) -> float:
    """斤量による遅れ[秒]。基準斤量なら0、重いほど正（＝損している）。

    指数に足し戻すことで「斤量が重いのに出したタイム」を正当に評価する。
    """
    k = SEC_PER_KG_PER_F if sec_per_kg_per_f is None else sec_per_kg_per_f
    if not kinryo or not distance or not k:
        return 0.0
    return round(k * (kinryo - BASE_KINRYO) * (distance / 200.0), 3)


# ---------------------------------------------------------------------------
# 位置取り（IDM の「位置取り」に相当する近似 — ただし IDM とは**逆向き**に使う）
#
# ⚠️ IDM 式の「外を回らされて損した馬は実力がタイムより上。指数に足し戻す」は
#    うちのデータで**否定された**（南関 101,227組）:
#        前走ロス 0.0〜秒 → 次走複勝 39.4% (lift 1.41)
#        前走ロス 1.5〜秒 → 次走複勝 22.2% (lift 0.80)
#    ロスが大きいほど次走も走らない＝**単調に逆**。理由は明快で、通過順だけから
#    作るこの値は結局「後ろにいた」を測っているだけで、「不運だった」と
#    「単に遅い」を区別できていない。**足し戻す補正としては使わない。**
#
# ✅ ただし**前走着順で層別しても効果が残った**ので、情報自体は本物:
#        前走1-3着  lift 1.08 → 0.89（幅0.19・弱い）
#        前走4-6着  lift 1.14 → 0.94（幅0.20）
#        前走7着以下 lift **1.39 → 0.89**（幅0.50・**最も強い**）
#    → **前走で大敗した馬のうち、それでも前々で運べていた馬は次走で巻き返す。**
#      着順だけでは「勝負になっていたのか」が分からない層で、この値が効く。
#      使い方は「損を足し戻す」ではなく「**前で運べたか**の指標」。
# ---------------------------------------------------------------------------

@dataclass
class PositionLoss:
    wide_m: float          # 推定の余分距離[m]
    sec: float             # 秒換算
    corners: int           # 使ったコーナー数
    note: str

    def __bool__(self) -> bool:
        return self.sec > 0


def position_loss(run: RunRecord, *, sec_per_100m: float = 6.7) -> PositionLoss | None:
    """通過順から「外を回らされたぶんの距離ロス」を推定する。

    考え方: 通過順が後ろの馬ほど、前が壁になって外を回らざるを得ない。
    各コーナーで **相対位置（0=先頭, 1=最後方）× 頭数** を「内から何頭ぶん外か」の
    上限とみなし、その半分を実際の外回り量として見積もる（全馬が最外を回るわけでは
    ないため）。

    ⚠️ これは**推定**であって実測ではない。前が開いていれば後方でも内を通れる。
    馬柱には進路情報が無いので、ここが限界。
    """
    cp = [p for p in (run.corner_pos or []) if p]
    n = run.field_size
    if not cp or not n or n < 2 or not run.distance:
        return None
    wide = 0.0
    for p in cp:
        rel = (p - 1) / (n - 1)                 # 0=先頭 1=最後方
        wide += rel * (n - 1) * 0.5 * WIDE_M_PER_HORSE
    sec = wide / 100.0 * sec_per_100m
    return PositionLoss(wide_m=round(wide, 1), sec=round(sec, 2), corners=len(cp),
                        note=f"{len(cp)}角で推定{wide:.0f}m外を回った")


# ---------------------------------------------------------------------------
# 出遅れの疑い（IDM の「出遅」に相当する近似）
# ---------------------------------------------------------------------------

def late_start(run: RunRecord, history: list[RunRecord],
               *, min_runs: int = 3, gap: float = 0.25) -> float:
    """その馬の普段の立ち上がりに比べ、1角の位置がどれだけ後ろだったか（0〜1）。

    その馬の過去走の1角相対位置の平均より `gap` 以上後ろなら「出遅れの疑い」。
    返り値は超過ぶん（0なら疑いなし）。

    ⚠️ 出遅れと「作戦として控えた」は区別できない。乗り替わりでも普通に起きる。
    """
    def rel(r: RunRecord) -> float | None:
        if not r.corner_pos or not r.field_size or r.field_size < 2:
            return None
        return (r.corner_pos[0] - 1) / (r.field_size - 1)

    now = rel(run)
    if now is None:
        return 0.0
    past = [x for x in (rel(r) for r in history if r is not run) if x is not None]
    if len(past) < min_runs:
        return 0.0
    base = sum(past) / len(past)
    return round(max(0.0, (now - base) - gap), 3)


# ---------------------------------------------------------------------------
# まとめ
# ---------------------------------------------------------------------------

#: 「前で運べていた」の上限[秒]。実測で lift が1を割る境界がここ。
#: 12頭立てだと 4番手(1.21秒)までが該当し、5番手(1.61秒)から外れる。
#: 0.0/0.5/1.0秒の各帯はいずれも lift>1 で、1.5秒〜だけが 0.89 に落ちる。
FORWARD_SEC = 1.5
#: 巻き返し判定の対象にする前走着順
BAD_FINISH = 7


def revenge(prev: RunRecord) -> bool:
    """前走大敗（7着以下）だが、**前々で運べていた**馬か。

    実測（南関 / 前走7着以下 44,826組・その層の次走複勝率 16.6% ＝ lift 1.00）:
        ロス 0.0〜0.5秒  n=2,730   23.1%  lift 1.39
        ロス 0.5〜1.0秒  n=4,123   22.5%  lift 1.35
        ロス 1.0〜1.5秒  n=5,467   20.4%  lift 1.22
        ロス 1.5秒〜     n=32,506  14.7%  lift 0.89   ← ここで割れる
    → 1.5秒未満をまとめると n=12,320 / 21.7% / **lift 1.31**。
    着順だけ見て消すと取りこぼす層をここで拾う。
    """
    if prev.finish_pos is None or prev.finish_pos < BAD_FINISH:
        return False
    pl = position_loss(prev)
    return bool(pl and pl.sec < FORWARD_SEC)


@dataclass
class Adjustment:
    kinryo_sec: float
    position_sec: float
    late: float

    @property
    def total_sec(self) -> float:
        """指数に足し戻す秒数。

        ⚠️ **position_sec は足さない。** IDM式の足し戻しは実測で否定された
        （モジュール冒頭の警告を参照）。位置取りは `revenge()` で別途使う。
        """
        return round(self.kinryo_sec, 3)

    @property
    def points(self) -> float:
        """指数のポイント換算（0.1秒 = 1pt）。"""
        return round(self.total_sec * 10, 1)

    def note(self) -> str:
        p = []
        if abs(self.kinryo_sec) >= 0.05:
            p.append(f"斤量{self.kinryo_sec:+.2f}秒")
        if self.position_sec >= 0.05:
            p.append(f"位置取り{self.position_sec:+.2f}秒")
        if self.late > 0:
            p.append(f"出遅れ疑い{self.late:.2f}")
        return " / ".join(p)


def adjust(run: RunRecord, history: list[RunRecord] | None = None,
           *, sec_per_kg_per_f: float | None = None) -> Adjustment:
    pl = position_loss(run)
    return Adjustment(
        kinryo_sec=kinryo_sec(run.kinryo, run.distance,
                              sec_per_kg_per_f=sec_per_kg_per_f),
        position_sec=pl.sec if pl else 0.0,
        late=late_start(run, history or []),
    )
