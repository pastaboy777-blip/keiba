"""適性データ ── 道悪実績・距離適性・種牡馬を取得。
【道悪・距離】各馬の近走seiseki(着順が取れる)を走査し、馬場条件×着順から道悪実績、
出走距離から距離適性を集計。今回距離との延長/短縮も判定。
【血統】/chihou/kettou/{rid} から種牡馬(sire)を全頭分抽出。
道悪巧者の穴サイン: 人気薄 かつ 道悪3着内率が高い(または道悪勝ちあり)。
標準ライブラリ + monogatari(_get/ARC/BASE/race_danwa/horse_recent_rids)。
"""
import re, os, sys
import monogatari as M

WET = ("稍重", "重", "不良")

def _seiseki_baba(h):
    m = re.search(r"(?:晴|曇|雨|小雨|雪|雷)・(不良|稍重|重|良)", h)
    return m.group(1) if m else None

def _horse_row_chaku(h, cd):
    idx = h.find(f'umacd="{cd}"')
    if idx < 0: return None
    start = h.rfind("<tr>", 0, idx); end = h.find("</tr>", idx)
    c = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", h[start:end], re.S)]
    if c and re.match(r"^\d+$", c[0]): return int(c[0])
    return None

def horse_aptitude(cd, n=6):
    """近nレースから道悪実績・距離実績を集計。"""
    rids = M.horse_recent_rids(cd, n)
    wet_run = wet_top3 = wet_win = 0
    dist_top3 = []
    for rid in rids:
        f = M._get(f"{M.BASE}/chihou/seiseki/{rid}", os.path.join(M.ARC, f"sei_{rid}.html"))
        h = open(f, encoding="utf-8", errors="replace").read()
        baba = _seiseki_baba(h)
        dm = re.search(r'racekyori">(\d+)', h)
        dist = int(dm.group(1)) if dm else None
        chaku = _horse_row_chaku(h, cd)
        if chaku is None: continue
        if baba in WET:
            wet_run += 1
            if chaku <= 3: wet_top3 += 1
            if chaku == 1: wet_win += 1
        if chaku <= 3 and dist: dist_top3.append(dist)
    return {"wet_run": wet_run, "wet_top3": wet_top3, "wet_win": wet_win,
            "dist_top3": dist_top3, "n": len(rids)}

def sires(rid):
    """血統ページ -> {umaban:{name,sire}}。出馬表順の馬名で対応付け。"""
    f = M._get(f"{M.BASE}/chihou/kettou/{rid}", os.path.join(M.ARC, f"ket_{rid}.html"))
    h = open(f, encoding="utf-8", errors="replace").read()
    out = {}
    # 各馬ブロック: 馬名 (性齢) 種牡馬 ...
    for m in re.finditer(r'umacd="\d+">\s*([ァ-ヴー]{2,})\s*</a>\s*\(([牡牝セ]\d)\)\s*([ァ-ヴA-Za-z一-龯ー]{2,})', h):
        out[m.group(1)] = {"seirei": m.group(2), "sire": m.group(3)}
    return out

def analyze(rid, unpop_from=6):
    danwa = M.race_danwa(rid)
    import cyokyo_ana as C
    od, rank = C.odds_rank(rid)
    dm = None
    f = os.path.join(M.ARC, f"sei_{rid}.html")
    if os.path.exists(f):
        dm = re.search(r'racekyori">(\d+)', open(f, encoding="utf-8", errors="replace").read())
    sr = {}
    try: sr = sires(rid)
    except Exception: pass
    rows = []
    for cd, info in danwa.items():
        ub = info.get("umaban");  pk = rank.get(ub, 99)
        ap = horse_aptitude(cd)
        rate = f"{ap['wet_top3']}/{ap['wet_run']}" if ap['wet_run'] else "道悪未"
        good = ap['wet_run'] >= 1 and ap['wet_top3'] / ap['wet_run'] >= 0.6
        ana = "★道悪巧者の穴" if (pk >= unpop_from and (ap['wet_win'] >= 1 or good)) else ""
        sire = sr.get(info.get("name"), {}).get("sire", "?")
        rows.append((ap['wet_top3'], ap['wet_run'], ub, info.get("name"), pk, od.get(ub), rate, sire, ana))
    rows.sort(key=lambda x: (-(x[0] / x[1] if x[1] else 0), -x[0], x[4]))
    return rows

if __name__ == "__main__":
    rid = sys.argv[1]
    print(f"=== 適性(道悪・距離・血統) {rid} ===")
    for wt3, wr, ub, nm, pk, o, rate, sire, ana in analyze(rid):
        star = "  " + ana if ana else ""
        print(f"  道悪{rate} | {ub:2}番 {nm} | {pk}人{o} | 父{sire}{star}")
