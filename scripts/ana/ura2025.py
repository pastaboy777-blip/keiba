"""2025年7-8月 大井：人気薄(単6番人気以下)が3着内に来た時のプロファイル。
脚質(1角通過・生)、上がり3F、距離、クラス、父、騎手、厩舎、具体例を集計。
"""
import re, os, json
from collections import Counter, defaultdict
import monogatari as M
import pedigree_line as P
import oi2025 as O

def parse_full(rid):
    f = os.path.join(M.ARC, f"sei_{rid}.html")
    M._get(f"{M.BASE}/chihou/seiseki/{rid}", f)
    h = open(f, encoding="utf-8", errors="replace").read()
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))
    md = re.search(r"発走\s*[\d:]+\s*(.*?)\s*(\d{3,4})m", t)
    if not md: return None
    dist = int(md.group(2)); kl = O.klass(md.group(1).strip())
    runners = []
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        row = m.group(1)
        if 'class="umaban"' not in row: continue
        tds = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(tds) < 16 or not re.match(r"^\d+$", tds[0]): continue
        chaku = int(tds[0])
        # 人気 = 上がり3F(XX.X)と単勝オッズ(X.X)に挟まれた整数
        ni = None
        for i in range(13, len(tds) - 1):
            if re.match(r"^\d{1,2}$", tds[i]) and re.match(r"^\d{2}\.\d$", tds[i - 1]) and re.match(r"^\d{1,3}\.\d$", tds[i + 1]):
                ni = i; break
        if ni is None: continue
        ninki = int(tds[ni]); agari = tds[ni - 1]
        tuka = next((x for x in tds if re.match(r"^\d+( +\d+)+$", x)), None)
        c1 = int(tuka.split()[0]) if tuka else None
        name = re.search(r"/db/uma/\d+[^>]*>\s*([ァ-ヴー]{2,})", row)
        kis = re.search(r"/db/kisyu/[^>]*>\s*([^<]{1,10})", row)
        kyu = [x for x in tds if re.search(r"[一-龯]", x) and " " in x]
        runners.append({"chaku": chaku, "ninki": ninki, "c1": c1,
                        "agari": float(agari) if agari else None,
                        "name": name.group(1) if name else None,
                        "kisyu": kis.group(1).strip() if kis else None,
                        "kyusya": (kyu[-1] if kyu else None)})
    return {"dist": dist, "klass": kl, "runners": runners}

def kyaku(c1):
    if c1 is None: return "?"
    if c1 == 1: return "逃げ"
    if c1 <= 3: return "先行"
    if c1 <= 6: return "好位"
    return "中団後方"

def run(minnk=6):
    hits = []; tot_ura = 0
    for date in O.DATES:
        for rid in O.oi_rids(date):
            r = parse_full(rid)
            if not r or not r["runners"]: continue
            try: sr = P.sires(rid)
            except Exception: sr = {}
            name2 = {v["name"]: v for v in sr.values()}
            for run_ in r["runners"]:
                if run_["ninki"] >= minnk:
                    tot_ura += 1
                    if run_["chaku"] <= 3:
                        ped = name2.get(run_["name"], {})
                        hits.append({**run_, "dist": r["dist"], "klass": r["klass"],
                                     "sire": ped.get("sire"), "line": P.line_of(ped.get("sire"), ped.get("gsire"))})
    n = len(hits)
    print(f"=== 2025年7-8月 大井：単{minnk}番人気以下が3着内 ===", flush=True)
    print(f"該当 {n}回 / 人気薄延べ出走 {tot_ura} → 出現率 {n/tot_ura*100:.1f}%", flush=True)
    print(f"人気内訳: {dict(sorted(Counter(h['ninki'] for h in hits).items()))}", flush=True)
    print(f"脚質(1角): {dict(Counter(kyaku(h['c1']) for h in hits))}", flush=True)
    fast = sum(1 for h in hits if h['agari'] and h['agari'] <= 38.0)
    print(f"上がり3F 38.0秒以内(速い脚): {fast}/{sum(1 for h in hits if h['agari'])}", flush=True)
    print(f"距離: {dict(sorted(Counter(h['dist'] for h in hits).items()))}", flush=True)
    print(f"クラス: {dict(Counter(h['klass'] for h in hits))}", flush=True)
    print(f"父系統: {dict(Counter(h['line'] for h in hits if h['line']))}", flush=True)
    def topc(key, k=8):
        return Counter(h[key] for h in hits if h[key]).most_common(k)
    print(f"父 TOP: {topc('sire')}", flush=True)
    print(f"騎手 TOP: {topc('kisyu')}", flush=True)
    print(f"厩舎 TOP: {topc('kyusya')}", flush=True)
    print("\n大穴の実例(単9番人気以下で3着内):", flush=True)
    for h in sorted(hits, key=lambda x: -x['ninki'])[:16]:
        print(f"  {h['ninki']:2d}人気→{h['chaku']}着 {h['name']} {h['dist']}m {h['klass']} {kyaku(h['c1'])} 父{re.sub(chr(12288),'',h['sire'] or '?')}", flush=True)
    json.dump(hits, open("ura_hits.json", "w"), ensure_ascii=False)

if __name__ == "__main__":
    import sys
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
