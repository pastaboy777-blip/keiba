"""末脚力スコア(大井の展開穴・事前予想版) ── 人気薄×高末脚をあぶり出す。
実測: 大井は勝ち馬の92%が上がり3位以内。人気薄×そのレース上がり1位=3着内55%(5.2倍)。
→ 事前に「近走で相対上がり順位が上位の馬(=末脚力)」をスコア化し、人気薄で高末脚を穴に。
末脚力 = 近走n走で各レースの上がり3F順位(相対)を集計。top2率が高いほど強い差し脚。
＋談話の差し脚ワードで微加点。人気は単勝オッズ順。
標準ライブラリ+monogatari。大井=場10。
"""
import re, os, sys
import monogatari as M

SASHI = ["差し", "追い込", "終い", "末脚", "上がり", "脚を溜め", "外を回", "鋭く", "伸び"]

def _agari_rank_in_race(rid, cd):
    """そのレースでの当該馬の上がり3F順位(1=最速) / 出走数。無ければNone。"""
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
    if mine is None or len(ags) < 4: return None
    rank = sorted(ags).index(mine) + 1
    return rank, len(ags)

def matomkyaku(cd, n=5):
    rids = M.horse_recent_rids(cd, n)
    top2 = runs = 0; pcts = []
    for rid in rids:
        r = _agari_rank_in_race(rid, cd)
        if not r: continue
        rank, field = r; runs += 1
        if rank <= 2: top2 += 1
        pcts.append(1 - (rank - 1) / (field - 1))     # 1=最速,0=最遅
    if not runs: return None
    return {"top2": top2, "runs": runs, "power": sum(pcts) / len(pcts)}

def analyze(rid, unpop_from=6):
    danwa = M.race_danwa(rid)
    import cyokyo_ana as C
    od, rank = C.odds_rank(rid)
    rows = []
    for cd, info in danwa.items():
        ub = info.get("umaban");  pk = rank.get(ub, 99)
        mk = matomkyaku(cd)
        pw = mk["power"] if mk else 0
        top2 = f"{mk['top2']}/{mk['runs']}" if mk else "-"
        sashi = any(w in (info.get("comment") or "") for w in SASHI)
        score = pw + (0.1 if sashi else 0)
        ana = "★末脚穴" if (pk >= unpop_from and mk and mk["runs"] >= 2 and
                          mk["power"] >= 0.7 and mk["top2"] >= 1) else ""
        rows.append((score, ub, info.get("name"), pk, od.get(ub), top2, pw, sashi, ana))
    rows.sort(key=lambda x: -x[0])
    return rows

if __name__ == "__main__":
    rid = sys.argv[1]
    print(f"=== 末脚力スコア(大井展開穴) {rid} ===")
    for sc, ub, nm, pk, o, top2, pw, sashi, ana in analyze(rid):
        s = " 差◯" if sashi else ""
        star = "  " + ana if ana else ""
        print(f"  末脚{pw:.2f} | {ub:2}番 {nm} | {pk}人{o} | 上位2率{top2}{s}{star}")
