"""大井 展開穴バックテスト(修正版) ── 全頭カバレッジ。
大井は談話が一部の馬しか無い→馬リストは結果ページ(全頭+umacd+人気+上がり)から取る。
事前末脚力は対象レースを除外した近走で計算。人気薄(6+)×高末脚を★フラグ→3着内で命中判定。
標準ライブラリ+monogatari+agari_power。
"""
import re, os, sys
import monogatari as M
import agari_power as A

MEETS = {"09": ["0608","0609","0610","0611","0612"], "10": ["0629","0630","0701","0702","0703"]}

def field(rid):
    """結果ページ -> [{umacd,umaban,chaku,nk,agari}] 全頭。"""
    f = M._get(f"{M.BASE}/chihou/seiseki/{rid}", os.path.join(M.ARC, f"kekka_{rid}.html"))
    h = open(f, encoding="utf-8", errors="replace").read()
    out = []
    for m in re.finditer(r"<tr>(.*?)</tr>", h, re.S):
        body = m.group(1)
        cm = re.search(r'/db/uma/(\d+)', body)
        c = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", body, re.S)]
        if not cm or len(c) < 15 or not re.match(r"^\d+$", c[0]): continue
        nmi = next((i for i, x in enumerate(c) if re.match(r"^[ァ-ヶー]{2,}$", x)), None)
        if nmi is None or nmi < 1 or not re.match(r"^\d+$", c[nmi - 1]): continue
        wi = next((i for i in range(nmi + 1, len(c)) if re.match(r"^[345]\d\d$", c[i])), None)
        nk = int(c[wi - 2]) if wi and wi >= 2 and re.match(r"^\d+$", c[wi - 2]) else None
        out.append({"umacd": cm.group(1), "umaban": int(c[nmi - 1]), "chaku": int(c[0]), "nk": nk})
    return out

def power_excl(cd, exclude_rid, n=6):
    """対象レースを除いた近走で末脚力。"""
    rids = [r for r in M.horse_recent_rids(cd, n) if r != exclude_rid][:5]
    top2 = runs = 0; pcts = []
    for rid in rids:
        r = A._agari_rank_in_race(rid, cd)
        if not r: continue
        rank, fld = r; runs += 1
        if rank <= 2: top2 += 1
        pcts.append(1 - (rank - 1) / (fld - 1))
    if not runs: return None
    return {"top2": top2, "runs": runs, "power": sum(pcts) / len(pcts)}

def run(kais):
    tot_f = tot_h = 0; base_f = base_h = 0
    for kai in kais:
        for i, mmdd in enumerate(MEETS[kai]):
            nn = i + 1
            for rr in range(1, 13):
                rid = f"2026{kai}10{nn:02d}{rr:02d}{mmdd}"
                try: fs = field(rid)
                except Exception: continue
                if len(fs) < 6: continue
                for r in fs:
                    if not r["nk"] or r["nk"] < 6: continue
                    base_f += 1
                    if r["chaku"] <= 3: base_h += 1
                    mk = power_excl(r["umacd"], rid)
                    if mk and mk["runs"] >= 2 and mk["power"] >= 0.7 and mk["top2"] >= 1:
                        tot_f += 1
                        if r["chaku"] <= 3: tot_h += 1
    print(f"\n=== 大井 回{'+'.join(kais)} 事前★末脚穴フラグ(全頭カバー・対象除外) ===", flush=True)
    print(f"人気薄(6+)ベースライン3着内: {base_h}/{base_f} ({base_h/base_f*100:.1f}%)" if base_f else "-")
    if tot_f:
        mult = (tot_h/tot_f)/(base_h/base_f) if base_f and base_h else 0
        print(f"★末脚穴フラグ: {tot_h}/{tot_f} ({tot_h/tot_f*100:.1f}%)  ベースライン比 {mult:.2f}x")
    else:
        print("★フラグ該当なし")

if __name__ == "__main__":
    run(sys.argv[1:] or ["10"])
