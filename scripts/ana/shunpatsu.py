"""瞬発力スコア（中央・芝の"一瞬の加速力"を数値化）。
中央は通過マスク→上がり3Fを"キレ"の代理に。生の上がりは持続と混ざるので:
  kire_rel = 各レースでの上がり順位(相対キレ、1位=最速差し脚)
  kire_abs = 絶対上がり時計のギア(芝33秒台=一級品)
  surf_w   = 芝=1.0 / ダ=0.7（瞬発力は芝の武器）
瞬発力 = mean( (0.5*kire_rel + 0.5*kire_abs) * surf_w )
※真の"一瞬(単一F)"は per-horse では取れず、上がり3Fが最細粒度。溜め度(後方)は通過マスクで近似不可
  →着順より上がり順位が大きく良い（=着<上がりで差し込んだ）レースに小加点でキレを補強。
標準ライブラリ + monogatari_cyuou(horse_recent_rids) + jra_bias(get)。
"""
import re, os, sys
import monogatari_cyuou as MC
import jra_bias as JB

def _abs_bonus(ag, dirt):
    t = ag - (1.0 if dirt else 0.0)   # ダートは1秒補正して芝スケールに寄せる
    if t <= 33.5: return 1.0
    if t <= 34.0: return 0.85
    if t <= 34.5: return 0.7
    if t <= 35.0: return 0.5
    if t <= 35.5: return 0.35
    return 0.2

def _race_agari(rid):
    """そのレースの [{umacd,chaku,agari}] と 芝/ダ。"""
    h = JB.get(rid)
    dm = re.search(r"(芝|ダ(?:ート)?)\s*\d{3,4}", h)
    dirt = bool(dm and "ダ" in dm.group(1))
    rows = []
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        cd = re.search(r"/db/uma/(\d+)", m.group(1))
        if not cd: continue
        c = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]
        if len(c) < 15 or not re.match(r"^\d+$", c[0]): continue
        # 上がり3F = 32.0〜42.9 の小数、人気(int)+オッズ(dec) の直前。範囲外(47等)は除外
        ag = None
        for j in range(len(c) - 1, 5, -1):
            if re.match(r"^(3[2-9]|4[0-2])\.\d$", c[j]): ag = float(c[j]); break
        if ag is None: continue
        rows.append({"umacd": cd.group(1), "chaku": int(c[0]), "agari": ag})
    return rows, dirt

def score(cd, exclude_rid=None, n=6):
    rids = [r for r in MC.horse_recent_rids(cd, n) if r != exclude_rid][:5]
    vals = []
    for rid in rids:
        rows, dirt = _race_agari(rid)
        if len(rows) < 5: continue
        order = sorted(rows, key=lambda r: r["agari"])
        rank = {x["umacd"]: i + 1 for i, x in enumerate(order)}
        me = next((x for x in rows if x["umacd"] == cd), None)
        if not me: continue
        nfield = len(rows)
        kire_rel = 1 - (rank[cd] - 1) / (nfield - 1)
        kire_abs = _abs_bonus(me["agari"], dirt)
        surf_w = 0.7 if dirt else 1.0
        # 着<上がり順位（差し込んだ）に小加点
        boost = 0.1 if me["chaku"] > rank[cd] else 0.0
        vals.append((0.5 * kire_rel + 0.5 * kire_abs + boost) * surf_w)
    if not vals: return None
    return {"score": sum(vals) / len(vals), "runs": len(vals)}

def analyze(rid):
    rows, dirt = _race_agari(rid)
    out = []
    for r in rows:
        s = score(r["umacd"], exclude_rid=rid)
        out.append((s["score"] if s else 0, r["umacd"], r["chaku"]))
    out.sort(reverse=True)
    return out

if __name__ == "__main__":
    rid = sys.argv[1]
    print(f"=== 瞬発力スコア {rid}（事前・対象除外） ===")
    for i, (sc, cd, chaku) in enumerate(analyze(rid), 1):
        print(f"  瞬発{sc:.2f} | umacd {cd} | 着{chaku}" + ("  ★スコア1位" if i == 1 else ""))
