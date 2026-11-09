"""JRA 展開バイアス検証（上がり3F代理）。中央も通過はマスク→上がり順位で前/差しを代理。
勝ち馬の上がり順位分布・人気薄台頭・平均勝ち人気で、その開催日の展開傾向を掴む。
rid = YYYY + 回(2) + 場(2) + 日次(2) + R(2)。標準ライブラリ + curl(kb.conf)。
"""
import re, os, subprocess, sys
SP = os.path.dirname(os.path.abspath(__file__)); BASE = "https://p.keibabook.co.jp"

def get(rid):
    f = os.path.join(SP, "cyarc", f"k_{rid}.html"); os.makedirs(os.path.join(SP, "cyarc"), exist_ok=True)
    if not os.path.exists(f) or os.path.getsize(f) < 3000:
        subprocess.run(["curl", "-s", "-L", "-K", os.path.join(SP, "kb.conf"),
                        f"{BASE}/cyuou/seiseki/{rid}", "-o", f], check=False)
    return open(f, encoding="utf-8", errors="replace").read()

def parse(rid):
    h = get(rid)
    if "/db/uma/" not in h: return None, []
    dist = None
    dm = re.search(r"(芝|ダート|ダ)\s*(\d{3,4})", h)
    rows = []
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        if "/db/uma/" not in m.group(1): continue
        c = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]
        if len(c) < 17 or not re.match(r"^\d+$", c[0]): continue
        nm = next((x for x in c if re.match(r"^[ァ-ヶー]{2,}$", x)), None)
        if not nm: continue
        # 上がり3F = 3x.x/4x.x decimal; 人気 = int cell after odds(dec)
        ag = None
        for j in range(len(c) - 1, 5, -1):
            if re.match(r"^[34]\d\.\d$", c[j]): ag = float(c[j]); agj = j; break
        nk = None
        # 人気は オッズ(小数)の次の整数、体重([345]dd)の手前
        for j in range(6, len(c)):
            if re.match(r"^\d+$", c[j]) and 1 <= int(c[j]) <= 18 and j+1 < len(c) and re.match(r"^\d+\.\d$", c[j+1]):
                nk = int(c[j])
        rows.append({"chaku": int(c[0]), "name": nm, "agari": ag, "nk": nk})
    return dist, rows

def analyze(label, head, days):
    from collections import Counter
    win_rank = Counter(); win_nk = []; fav_win = fav_run = 0; ana_win = 0; nr = 0
    for day in days:
        for rr in range(1, 13):
            rid = f"{head}{day}{rr:02d}"
            _, rows = parse(rid)
            ags = [r for r in rows if r["agari"] is not None]
            if len(ags) < 5: continue
            nr += 1
            order = sorted(ags, key=lambda r: r["agari"])
            rankmap = {id(r): k + 1 for k, r in enumerate(order)}
            win = next((r for r in rows if r["chaku"] == 1), None)
            if win and id(win) in rankmap:
                rk = rankmap[id(win)]; n = len(order)
                lab = "上1" if rk == 1 else "上2-3" if rk <= 3 else "上位半" if rk <= n/2 else "上り下位(前)"
                win_rank[lab] += 1
                if win["nk"]: win_nk.append(win["nk"]); fav_run += 1
                if win["nk"] == 1: fav_win += 1
                if win["nk"] and win["nk"] >= 6: ana_win += 1
    print(f"=== {label} ({nr}R) ===")
    print("勝ち脚質(上がり順位):", dict(win_rank))
    if win_nk:
        print(f"平均勝ち人気 {sum(win_nk)/len(win_nk):.1f} / 1番人気 {fav_win}/{fav_run} / 人気薄(6+)勝利 {ana_win}/{fav_run}")

if __name__ == "__main__":
    analyze("小倉 土(7/18)", "20260203", ["07"])
    analyze("小倉 日(7/19)", "20260203", ["08"])
