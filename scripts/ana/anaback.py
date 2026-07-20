"""穴逆算エンジン：展開→想定上がり→"今の馬場で"その上がりを出せる人気薄=穴 を選ぶ。
主役は展開。手順:
 1) tenkai_ooiで逃げ頭数→ペース→前傾/後傾(＋馬場)で「差し馬場か前残りか」を判定。
 2) 各馬の近走から【今日と同じ馬場ティア(wet=稍重/重/不良 / dry=良)】での"直近ベスト上がり"を抽出（馬場補正）。
 3) 前傾/差し馬場なら: 馬場一致で速い上がりを出せる人気薄(単5番人気以下)を穴候補に。
    前残り/後傾なら: 前で立ち回れる(1角平均が前)の人気薄を穴候補に。
上がりは必ず馬場とセット。生タイムでなく"今日の馬場で出した直近の上がり"で評価。
"""
import re, os, sys
import monogatari as M
import tenkai_ooi as T
import hidden as H
import cyokyo_ana as C

WET = ("稍重", "重", "不良")

def horse_agari(cd, wet, nrecent=8):
    """近走(直近nrecent)から、今日の馬場ティアでの最速上がりと平均1角を返す。"""
    races = sorted(H.parse_db_races(cd), key=lambda r: (r[0], r[1], r[2]), reverse=True)[:nrecent]
    tier_ags = []; allc1 = []
    for (y, mo, dy, baba, dist, pace, ag, c1, ch, nk) in races:
        if c1: allc1.append(c1)
        same = (baba in WET) if wet else (baba == "良")
        if same and ag: tier_ags.append(ag)
    best = min(tier_ags) if tier_ags else None
    avg1 = sum(allc1) / len(allc1) if allc1 else 9.9
    return best, avg1, len(tier_ags)

def run(rid, baba):
    wet = baba in WET
    horses, front, pace, _ = T.analyze(rid)
    nf = len(front)
    # 前傾/後傾の想定（馬場込み）※稍重/重/不良は当日差し馬場を優先(前が止まる)
    if wet:
        ldr = "逃げ不在で緩むが" if nf == 0 else f"逃げ{nf}頭で"
        shape = f"{baba}＝当日差し馬場。{ldr}前は止まりやすい→【好位差し・中団】本線"
        mode = "sashi"
    elif nf >= 3:
        shape = "多頭数で前傾ラップ→【差し】有利"
        mode = "sashi"
    elif nf <= 1:
        shape = "スロー/単騎で後傾→【前・好位】残り本線"
        mode = "nige"
    else:
        shape = "ミドル→好位差し"
        mode = "sashi"
    try: od, rank = C.odds_rank(rid)
    except Exception: od, rank = {}, {}
    rows = []
    danwa = M.race_danwa(rid)
    cdby = {info.get("umaban"): cd for cd, info in danwa.items()}
    for h in horses:
        ub = h["ub"]; cd = cdby.get(ub)
        best, avg1, n = (None, h.get("avg1", 9.9), 0)
        if cd: best, avg1, n = horse_agari(cd, wet)
        nk = rank.get(ub, 99)
        rows.append({"ub": ub, "name": h["name"], "best": best, "avg1": avg1, "n": n, "nk": nk})
    # 想定上がり = 馬場一致ベスト上がりの上位3頭の中央値目安
    bests = sorted([r["best"] for r in rows if r["best"]])
    band = bests[:3]
    print(f"=== {rid} 穴逆算（馬場{baba}） ===")
    print(f"展開: 逃げ争い{nf}頭 / {pace} → {shape}")
    if band: print(f"想定される上がり水準（{'重馬場' if wet else '良'}での近走ベスト上位）: {band}  ← この脚を"+("人気薄で持つ馬が穴" if mode=="sashi" else "前で持つ人気薄が穴"))
    print("穴候補（単5番人気以下）:")
    if mode == "sashi":
        cand = [r for r in rows if r["nk"] >= 5 and r["best"]]
        cand.sort(key=lambda r: (r["best"], -r["nk"]))  # 馬場一致で速い上がり順
        for r in cand[:5]:
            print(f"  {r['nk']:>2}人気 {r['ub']:>2}番 {r['name']:<11} 馬場一致ベスト上がり{r['best']}({r['n']}走) 1角平均{r['avg1']:.1f}")
    else:
        cand = [r for r in rows if r["nk"] >= 5 and r["avg1"] <= 4.5]
        cand.sort(key=lambda r: (r["avg1"], -r["nk"]))
        for r in cand[:5]:
            print(f"  {r['nk']:>2}人気 {r['ub']:>2}番 {r['name']:<11} 前受け1角平均{r['avg1']:.1f} 馬場一致上がり{r['best']}")

if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "稍重")
