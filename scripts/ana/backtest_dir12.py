"""大井 方向1(前受け人気馬フェード) + 方向2(絶対上がり) バックテスト。
結果ページ全頭カバー、対象レース除外。各馬の近走から:
  power    = 相対上がり順位の平均(1=最速…0=最遅)。低い=前受け/末脚無いタイプ。
  best_ag  = 近走の自己上がり3F最速値(絶対時計)。
測定(回09+10):
  方向1: 人気馬(nk<=5) 全体 vs そのうち power<=0.40(前受けタイプ) の3着内率。
         前受け人気馬が下回れば"フェード"の裏が取れる。
  方向2: 人気薄(nk>=6) 全体 vs best_ag<=37.5(絶対末脚速い) の3着内率。
標準ライブラリ+monogatari+agari_power。
"""
import re, os, sys
import monogatari as M
import agari_power as A

MEETS = {"09": ["0608","0609","0610","0611","0612"], "10": ["0629","0630","0701","0702","0703"]}

def field(rid):
    f = M._get(f"{M.BASE}/chihou/seiseki/{rid}", os.path.join(M.ARC, f"kekka_{rid}.html"))
    h = open(f, encoding="utf-8", errors="replace").read()
    out = []
    for m in re.finditer(r"<tr>(.*?)</tr>", h, re.S):
        body = m.group(1); cm = re.search(r"/db/uma/(\d+)", body)
        c = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", body, re.S)]
        if not cm or len(c) < 15 or not re.match(r"^\d+$", c[0]): continue
        nmi = next((i for i, x in enumerate(c) if re.match(r"^[ァ-ヶー]{2,}$", x)), None)
        if nmi is None or nmi < 1 or not re.match(r"^\d+$", c[nmi - 1]): continue
        wi = next((i for i in range(nmi + 1, len(c)) if re.match(r"^[345]\d\d$", c[i])), None)
        nk = int(c[wi - 2]) if wi and wi >= 2 and re.match(r"^\d+$", c[wi - 2]) else None
        out.append({"umacd": cm.group(1), "chaku": int(c[0]), "nk": nk})
    return out

def profile(cd, exclude_rid, n=6):
    rids = [r for r in M.horse_recent_rids(cd, n) if r != exclude_rid][:5]
    pcts = []; agaris = []
    for rid in rids:
        # rank + own agari in that race
        f = M._get(f"{M.BASE}/chihou/seiseki/{rid}", os.path.join(M.ARC, f"kekka_{rid}.html"))
        h = open(f, encoding="utf-8", errors="replace").read()
        ags = []; mine = None
        for m in re.finditer(r"<tr>(.*?)</tr>", h, re.S):
            c = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]
            if len(c) < 15 or not re.match(r"^\d+$", c[0]): continue
            nmi = next((i for i, x in enumerate(c) if re.match(r"^[ァ-ヶー]{2,}$", x)), None)
            if nmi is None: continue
            wi = next((i for i in range(nmi + 1, len(c)) if re.match(r"^[345]\d\d$", c[i])), None)
            ag = None
            if wi:
                for j in range(nmi + 1, wi - 1):
                    if re.match(r"^[34]\d\.\d$", c[j]): ag = float(c[j])
            if ag is None: continue
            ags.append(ag)
            if f'umacd="{cd}"' in m.group(1): mine = ag
        if mine is None or len(ags) < 4: continue
        rank = sorted(ags).index(mine) + 1
        pcts.append(1 - (rank - 1) / (len(ags) - 1)); agaris.append(mine)
    if not pcts: return None
    return {"power": sum(pcts) / len(pcts), "best_ag": min(agaris), "runs": len(pcts)}

def run(kais):
    fav_f = fav_h = 0; favlow_f = favlow_h = 0        # 方向1
    un_f = un_h = 0; unfast_f = unfast_h = 0          # 方向2
    for kai in kais:
        for i, mmdd in enumerate(MEETS[kai]):
            nn = i + 1
            for rr in range(1, 13):
                rid = f"2026{kai}10{nn:02d}{rr:02d}{mmdd}"
                try: fs = field(rid)
                except Exception: continue
                if len(fs) < 6: continue
                for r in fs:
                    if not r["nk"]: continue
                    p = profile(r["umacd"], rid)
                    if not p or p["runs"] < 2: continue
                    hit = r["chaku"] <= 3
                    if r["nk"] <= 5:
                        fav_f += 1; fav_h += hit
                        if p["power"] <= 0.40:
                            favlow_f += 1; favlow_h += hit
                    if r["nk"] >= 6:
                        un_f += 1; un_h += hit
                        if p["best_ag"] <= 37.5:
                            unfast_f += 1; unfast_h += hit
    def line(nm, h, f, base=None):
        if not f: return f"{nm}: 該当なし"
        s = f"{nm}: {h}/{f} ({h/f*100:.1f}%)"
        if base: s += f"  比 {(h/f)/base:.2f}x"
        return s
    print(f"\n=== 大井 回{'+'.join(kais)} 方向1・2 バックテスト ===", flush=True)
    fb = fav_h/fav_f if fav_f else 0
    print("[方向1 前受け人気馬フェード]")
    print(" ", line("人気馬(nk<=5)全体", fav_h, fav_f))
    print(" ", line("  └ 前受けタイプ(power<=0.40)", favlow_h, favlow_f, fb))
    ub = un_h/un_f if un_f else 0
    print("[方向2 絶対上がり]")
    print(" ", line("人気薄(nk>=6)全体", un_h, un_f))
    print(" ", line("  └ 絶対上がり速(best<=37.5)", unfast_h, unfast_f, ub))

if __name__ == "__main__":
    run(sys.argv[1:] or ["09", "10"])
