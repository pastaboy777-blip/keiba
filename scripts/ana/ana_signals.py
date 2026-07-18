"""穴サイン命中率トラッキングDB ── どの穴サインが本当に効くかを検証。
各レースで下記の穴サインを検出し、フラグした人気薄馬が結果3着内に来たかを記録。
signals_db.json に累積し、サインごとの命中率(3着内)を集計する。
サイン: kehai(気配好転) / story(上昇物語) / doaku(道悪巧者) / stable2(厩舎2頭出し人気薄) / kogata(小型×人気薄)
標準ライブラリ + kehai_score/ana_story/aptitude/monogatari。
"""
import re, os, sys, json
import monogatari as M
import cyokyo_ana as C
import kehai_score, ana_story, aptitude

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signals_db.json")
WET = ("稍重", "重", "不良")

def stable2_unpop(rid, unpop_from=6):
    """厩舎2頭出しの人気薄側(人気from以下)を返す。"""
    h = open(M._get(f"{M.BASE}/chihou/danwa/1/{rid}", os.path.join(M.ARC, f"danwa_{rid}.html")),
             encoding="utf-8", errors="replace").read()
    od, rank = C.odds_rank(rid)
    from collections import defaultdict
    g = defaultdict(list)
    for m in re.finditer(r'<td class="umaban">(\d+)</td>.*?umacd="\d+">([^<]+)</a>.*?<td class="danwa"><p>(.*?)</p>', h, re.S):
        ub = int(m.group(1)); body = m.group(3)
        mt = re.search(r"[【　]?([一-龯ぁ-んァ-ヶ]{1,4})師[】―—－]", body)
        if mt: g[mt.group(1)].append(ub)
    out = []
    for t, ubs in g.items():
        if len(ubs) >= 2:
            unpop = [u for u in ubs if rank.get(u, 99) >= unpop_from]
            # 相方より人気が下の馬のみ
            best = min(ubs, key=lambda u: rank.get(u, 99))
            for u in unpop:
                if u != best: out.append(u)
    return set(out)

def kogata_unpop(rid, unpop_from=6):
    """小型(≤440)×人気薄。体重は結果ページ(なければ出馬表)から。"""
    od, rank = C.odds_rank(rid)
    f = os.path.join(M.ARC, f"kekka_{rid}.html")
    if not os.path.exists(f):
        f = os.path.join(M.ARC, f"sei_{rid}.html"); M._get(f"{M.BASE}/chihou/seiseki/{rid}", f)
    h = open(f, encoding="utf-8", errors="replace").read()
    out = set()
    for m in re.finditer(r'<tr>(.*?)</tr>', h, re.S):
        c = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]
        if len(c) < 15: continue
        nmi = next((i for i, x in enumerate(c) if re.match(r"^[ァ-ヶー]{2,}$", x)), None)
        if nmi is None or nmi < 1 or not re.match(r"^\d+$", c[nmi - 1]): continue
        ub = int(c[nmi - 1])
        wt = next((int(x) for x in c[nmi + 1:] if re.match(r"^[34]\d\d$", x)), None)
        if wt and wt <= 440 and rank.get(ub, 99) >= unpop_from: out.add(ub)
    return out

def result_top3(rid):
    f = os.path.join(M.ARC, f"kekka_{rid}.html"); M._get(f"{M.BASE}/chihou/seiseki/{rid}", f)
    h = open(f, encoding="utf-8", errors="replace").read()
    top = {}
    for m in re.finditer(r'<tr>(.*?)</tr>', h, re.S):
        c = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]
        if len(c) < 15 or not re.match(r"^\d+$", c[0]): continue
        nmi = next((i for i, x in enumerate(c) if re.match(r"^[ァ-ヶー]{2,}$", x)), None)
        if nmi is None or nmi < 1 or not re.match(r"^\d+$", c[nmi - 1]): continue
        ch = int(c[0])
        if ch <= 3: top[ch] = int(c[nmi - 1])
    return set(top.values()) if len(top) >= 3 else None

def flags(rid):
    out = {}
    out["kehai"] = {ub for sc, ub, *_ , ana in kehai_score.analyze(rid) if ana}
    out["story"] = {ub for sc, ub, *_ , ana in ana_story.analyze(rid) if ana}
    out["doaku"] = {r[2] for r in aptitude.analyze(rid) if r[-1]}
    out["stable2"] = stable2_unpop(rid)
    out["kogata"] = kogata_unpop(rid)
    return out

def record(rid):
    top3 = result_top3(rid)
    if not top3: return None
    fl = flags(rid)
    db = json.load(open(DB)) if os.path.exists(DB) else {"races": {}}
    db["races"][rid] = {k: sorted(v) for k, v in fl.items()}
    db["races"][rid]["_top3"] = sorted(top3)
    json.dump(db, open(DB, "w"), ensure_ascii=False, indent=1)
    return fl, top3

def summarize():
    db = json.load(open(DB))
    agg = {}
    for rid, rec in db["races"].items():
        top3 = set(rec.get("_top3", []))
        for sign, ubs in rec.items():
            if sign == "_top3": continue
            a = agg.setdefault(sign, {"flag": 0, "hit": 0, "races": 0})
            if ubs: a["races"] += 1
            for ub in ubs:
                a["flag"] += 1
                if ub in top3: a["hit"] += 1
    print("=== 穴サイン命中率(3着内) ===")
    for sign, a in sorted(agg.items(), key=lambda x: -(x[1]["hit"] / x[1]["flag"] if x[1]["flag"] else 0)):
        rate = a["hit"] / a["flag"] * 100 if a["flag"] else 0
        print(f"  {sign:9} 命中 {a['hit']}/{a['flag']} ({rate:.0f}%)  出現{a['races']}R")

if __name__ == "__main__":
    if sys.argv[1] == "sum":
        summarize()
    else:
        for rid in sys.argv[1:]:
            r = record(rid)
            print(rid, "記録:", {k: sorted(v) for k, v in r[0].items()} if r else "結果未確定", "| top3", sorted(r[1]) if r else "-")
