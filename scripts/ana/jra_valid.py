"""JRA 7/18-19（函館・小倉・福島）で 4角"最内 vs 非最内" 複勝率を 芝/ダ×馬場 別に検証。
中央seisekiのコーナー通過は詳細(併走()つき)＝レーン内外が正確に取れる。
"""
import re, os, sys
from collections import defaultdict
import monogatari as M
import corner as C

# (コース名, head+日次10桁) 7/18 と 7/19(日次+1)
MEETS = {
 "7/18": [("函館","2026010911"),("小倉","2026020307"),("福島","2026020607")],
 "7/19": [("函館","2026010912"),("小倉","2026020308"),("福島","2026020608")],
}

def race(rid):
    f = os.path.join(M.ARC, f"csei_{rid}.html")
    M._get(f"{M.BASE}/cyuou/seiseki/{rid}", f)
    h = open(f, encoding="utf-8", errors="replace").read()
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))
    ms = re.search(r"\((芝|ダ)[Ａ-ＺA-Z]?・", t)
    surf = ms.group(1) if ms else "?"
    mb = re.search(r"(?:晴|曇|雨|小雨|雪|雷)・(良|稍重|重|不良)", t)
    cond = mb.group(1) if mb else "?"
    rows = []
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        row = m.group(1)
        if 'class="umaban"' not in row: continue
        tds = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(tds) < 10 or not re.match(r"^\d+$", tds[0]): continue
        ub = int(re.search(r'class="umaban">(\d+)', row).group(1))
        rows.append({"chaku": int(tds[0]), "ub": ub})
    try:
        cs = C.corners(rid, path=f); c4 = {ub: ln for gr, ln, ub in C.parse_line(cs.get(4, ""))}
    except Exception:
        c4 = {}
    for r in rows: r["lane4"] = c4.get(r["ub"])
    return surf, cond, rows

def wet(c): return "重系" if c in ("稍重", "重", "不良") else "良" if c == "良" else "?"

def run():
    bysurf = defaultdict(lambda: [defaultdict(lambda:[0,0]), defaultdict(lambda:[0,0])])  # surf -> [inner,nonin] by baba
    bycourse = defaultdict(lambda: [defaultdict(lambda:[0,0]), defaultdict(lambda:[0,0])])
    nr = 0; laned = 0
    for day, meets in MEETS.items():
        for cname, head in meets:
            for rr in range(1, 13):
                rid = f"{head}{rr:02d}"
                surf, cond, rows = race(rid)
                if not rows: continue
                nr += 1; bk = wet(cond)
                if any(r["lane4"] is not None for r in rows): laned += 1
                for r in rows:
                    if r["lane4"] is None: continue
                    good = 1 if r["chaku"] <= 3 else 0
                    idx = 0 if r["lane4"] == 0 else 1
                    bysurf[surf][idx][bk][0] += 1; bysurf[surf][idx][bk][1] += good
                    bycourse[cname][idx][bk][0] += 1; bycourse[cname][idx][bk][1] += good
    def pc(v): return f"{v[1]}/{v[0]}={v[1]/v[0]*100:.0f}%" if v[0] else "-"
    print(f"=== JRA 7/18-19（{nr}R, 4角レーン取得{laned}R）最内 vs 非最内 複勝率 ===", flush=True)
    print("■ 芝/ダ × 馬場 別:", flush=True)
    for surf in ["芝", "ダ"]:
        for bk in ["良", "重系"]:
            i, n = bysurf[surf][0][bk], bysurf[surf][1][bk]
            if i[0] or n[0]: print(f"  {surf}・{bk}: 最内 {pc(i)} ／ 非最内 {pc(n)}", flush=True)
    print("■ コース別(良のみ):", flush=True)
    for cname in ["函館", "小倉", "福島"]:
        i, n = bycourse[cname][0]["良"], bycourse[cname][1]["良"]
        if i[0] or n[0]: print(f"  {cname}芝ダ混・良: 最内 {pc(i)} ／ 非最内 {pc(n)}", flush=True)

if __name__ == "__main__":
    run()
