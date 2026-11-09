"""大井 展開穴の実測(上り3F代理版)。
大井の結果ページは通過順が"****"でマスク→脚質は上り3F(agari)で代理:
  上り最速級=差し脚を使った馬。勝ち馬の上り順位で「差し天国か前残りか」を判定。
指標:
  ・勝ち馬の上り順位分布(1位=最速差し … 下位=前で粘り)
  ・展開穴A: 人気薄(6+)×上り1位 が3着内に来た率
  ・展開穴B(前残り): 人気薄×上り下位(=前で粘った)が3着内に来た率
  ・比較用: 小型(≤440)×人気薄 の3着内率、人気薄ベースライン
rid=2026 KK 10 NN RR MMDD。標準ライブラリ+monogatari。
"""
import re, os, sys
import monogatari as M

MEETS = {"09": ["0608","0609","0610","0611","0612"], "10": ["0629","0630","0701","0702","0703"]}

def parse(rid):
    f = M._get(f"{M.BASE}/chihou/seiseki/{rid}", os.path.join(M.ARC, f"kekka_{rid}.html"))
    h = open(f, encoding="utf-8", errors="replace").read()
    rows = []
    for m in re.finditer(r"<tr>(.*?)</tr>", h, re.S):
        c = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]
        if len(c) < 15 or not re.match(r"^\d+$", c[0]): continue
        nmi = next((i for i, x in enumerate(c) if re.match(r"^[ァ-ヶー]{2,}$", x)), None)
        if nmi is None: continue
        wi = next((i for i in range(nmi + 1, len(c)) if re.match(r"^[345]\d\d$", c[i])), None)
        if wi is None: continue
        nk = int(c[wi - 2]) if wi >= 2 and re.match(r"^\d+$", c[wi - 2]) else None
        wt = int(c[wi])
        # 上り3F = 3x.x〜4x.x の小数、通過(masked)と人気の間、体重より前
        agari = None
        for j in range(nmi + 1, wi - 2):
            if re.match(r"^[34]\d\.\d$", c[j]): agari = float(c[j])
        rows.append({"chaku": int(c[0]), "nk": nk, "wt": wt, "agari": agari})
    return rows

def run(kais):
    win_agrank = {}          # 勝ち馬の上り順位分布
    nraces = 0
    baseF = baseH = 0        # 人気薄ベースライン
    aF = aH = 0              # 展開穴A: 人気薄×上り1位
    bF = bH = 0              # 展開穴B: 人気薄×上り下位(前残り)
    kF = kH = 0              # 小型×人気薄
    for kai in kais:
        for i, mmdd in enumerate(MEETS[kai]):
            nn = i + 1
            for rr in range(1, 13):
                rid = f"2026{kai}10{nn:02d}{rr:02d}{mmdd}"
                try: rows = parse(rid)
                except Exception: continue
                if len(rows) < 5: continue
                ag = [r for r in rows if r["agari"] is not None]
                if len(ag) < 5: continue
                nraces += 1
                order = sorted(ag, key=lambda r: r["agari"])       # 上り速い順
                rankmap = {id(r): k + 1 for k, r in enumerate(order)}
                nfield = len(order)
                top3 = {r["chaku"] for r in rows if r["chaku"] <= 3}
                win = next((r for r in rows if r["chaku"] == 1), None)
                if win and id(win) in rankmap:
                    rk = rankmap[id(win)]
                    lab = "上1" if rk == 1 else "上2-3" if rk <= 3 else "上位半" if rk <= nfield/2 else "上り下位"
                    win_agrank[lab] = win_agrank.get(lab, 0) + 1
                for r in rows:
                    if not r["nk"] or r["nk"] < 6: continue
                    baseF += 1
                    if r["chaku"] <= 3: baseH += 1
                    rk = rankmap.get(id(r))
                    if rk == 1:
                        aF += 1
                        if r["chaku"] <= 3: aH += 1
                    if rk and rk > nfield * 0.6:
                        bF += 1
                        if r["chaku"] <= 3: bH += 1
                    if r["wt"] and r["wt"] <= 440:
                        kF += 1
                        if r["chaku"] <= 3: kH += 1
    def pct(h, f): return f"{h}/{f} ({h/f*100:.0f}%)" if f else "-"
    print(f"=== 大井 回{'+'.join(kais)} 展開穴実測({nraces}R・上り3F代理) ===")
    print("勝ち馬の上り順位:", {k: win_agrank[k] for k in ["上1","上2-3","上位半","上り下位"] if k in win_agrank})
    base = baseH / baseF if baseF else 0
    print(f"人気薄(6+)ベースライン3着内: {pct(baseH,baseF)}")
    print(f"[展開穴A] 人気薄×上り1位(最速差し): {pct(aH,aF)}  倍率 {(aH/aF)/base:.2f}x" if aF and base else "A: -")
    print(f"[展開穴B] 人気薄×上り下位(前残り): {pct(bH,bF)}  倍率 {(bH/bF)/base:.2f}x" if bF and base else "B: -")
    print(f"[比較] 小型≤440×人気薄: {pct(kH,kF)}  倍率 {(kH/kF)/base:.2f}x" if kF and base else "小型: -")

if __name__ == "__main__":
    run(sys.argv[1:] or ["09", "10"])
