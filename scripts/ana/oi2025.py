"""note特典：2025年7-8月 大井で好走した 血統(父/系統)・騎手・厩舎 を 距離×クラス別に集計。
好走=着順3以内(複勝圏)。複勝率=好走/出走。データは全公開成績(seiseki)＋血統(kettou)。
出力: agg.json（距離別/クラス別/全体 の sire/line/jockey/trainer カウンタ）＋人間可読サマリ。
"""
import re, os, sys, json
from collections import defaultdict
import monogatari as M
import pedigree_line as P

DATES = ["20250701","20250702","20250703","20250704",
         "20250714","20250715","20250716","20250717","20250718",
         "20250810","20250811","20250812","20250813","20250814","20250815"]

def oi_rids(date):
    f = os.path.join(M.ARC, f"nittei_{date}.html")
    M._get(f"{M.BASE}/chihou/nittei/{date}", f)
    h = open(f, encoding="utf-8", errors="replace").read()
    rids = sorted(set(r for r in re.findall(r"/chihou/seiseki/(\d{16})", h) if r[6:8] == "10"))
    return rids

def zen2han(s):
    return s.translate(str.maketrans("ＡＢＣＤ０１２３４５６７８９","ABCD0123456789"))

def klass(cond):
    c = zen2han(cond)
    ijou = "以上" in c
    if re.search(r"2歳", c) and not ijou: return "2歳"
    if re.search(r"3歳", c) and not ijou: return "3歳"
    if re.search(r"A[12]|オープン|重賞|Ａ", c) or "A" in c: return "A・OP"
    if "B" in c: return "B級"
    if "C" in c: return "C級"
    return "その他"

def parse_seiseki(rid):
    f = os.path.join(M.ARC, f"sei_{rid}.html")
    M._get(f"{M.BASE}/chihou/seiseki/{rid}", f)
    h = open(f, encoding="utf-8", errors="replace").read()
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))
    md = re.search(r"発走\s*[\d:]+\s*(.*?)\s*(\d{3,4})m", t)
    if not md: return None
    cond = md.group(1).strip(); dist = int(md.group(2)); kl = klass(cond)
    runners = []
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        row = m.group(1)
        if 'class="umaban"' not in row: continue
        tds = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(tds) < 16 or not re.match(r"^\d+$", tds[0]): continue
        chaku = int(tds[0])
        name = re.search(r"/db/uma/\d+[^>]*>\s*([ァ-ヴー]{2,})", row)
        kis = re.search(r"/db/kisyu/[^>]*>\s*([^<]{1,10})", row)
        kyu = [x for x in tds if re.search(r"[一-龯]", x) and " " in x]
        runners.append({
            "chaku": chaku,
            "name": name.group(1) if name else None,
            "kisyu": kis.group(1).strip() if kis else None,
            "kyusya": kyu[-1] if kyu else None,
        })
    return {"dist": dist, "cond": cond, "klass": kl, "runners": runners}

def add(counter, key, good):
    if not key: return
    counter[key][0] += 1
    counter[key][1] += good

def run():
    # dims: "ALL", f"D{dist}", f"K{klass}", f"D{dist}|K{klass}"
    agg = {"sire": defaultdict(lambda: defaultdict(lambda: [0, 0])),
           "line": defaultdict(lambda: defaultdict(lambda: [0, 0])),
           "kisyu": defaultdict(lambda: defaultdict(lambda: [0, 0])),
           "kyusya": defaultdict(lambda: defaultdict(lambda: [0, 0]))}
    nr = 0
    for date in DATES:
        for rid in oi_rids(date):
            r = parse_seiseki(rid)
            if not r or not r["runners"]: continue
            try: sr = P.sires(rid)
            except Exception: sr = {}
            name2 = {v["name"]: v for v in sr.values()}
            nr += 1
            dims = ["ALL", f"D{r['dist']}", f"K{r['klass']}", f"D{r['dist']}|K{r['klass']}"]
            for run_ in r["runners"]:
                good = 1 if run_["chaku"] <= 3 else 0
                nm = run_["name"]; ped = name2.get(nm, {})
                sire = ped.get("sire"); gsire = ped.get("gsire")
                line = P.line_of(sire, gsire)
                for d in dims:
                    add(agg["sire"][d], sire, good)
                    add(agg["line"][d], line, good)
                    add(agg["kisyu"][d], run_["kisyu"], good)
                    add(agg["kyusya"][d], run_["kyusya"], good)
    # to plain dict
    out = {"nr": nr, "dates": DATES}
    for cat in agg:
        out[cat] = {dim: dict(v) for dim, v in agg[cat].items()}
    json.dump(out, open("agg.json", "w"), ensure_ascii=False)
    # サマリ: 全体トップ
    def top(cat, dim, by="good", minrun=1, n=8):
        d = out[cat].get(dim, {})
        items = [(k, v[1], v[0], v[1]/v[0]) for k, v in d.items() if k and v[0] >= minrun]
        items.sort(key=lambda x: (x[1] if by == "good" else x[3]), reverse=True)
        return items[:n]
    print(f"=== 大井 2025年7-8月 {nr}R 集計 ===", flush=True)
    for cat, lbl in [("kisyu","騎手"),("kyusya","厩舎"),("sire","父"),("line","父系統")]:
        print(f"\n【{lbl}】全体 好走数トップ:", flush=True)
        for k, g, run_, rate in top(cat, "ALL", "good", 1, 8):
            print(f"  {k}: 好走{g}/{run_} ({rate*100:.0f}%)", flush=True)

if __name__ == "__main__":
    run()
