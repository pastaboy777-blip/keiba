"""大井 展開予想で【軸】と【穴】の精度を検証・最適化する。
・軸 = 高確率で3着内に来る本命候補（複数ルール比較）
・穴 = 人気薄(単人気>=5)で好走する馬を展開から拾えるか（複数ルール比較）
result()は seiseki の 通過はmask なので使わず、着順・馬番・単人気だけ取り、
各馬の脚質(role)は tenkai_ooi.analyze の近5走ベースを使う（＝予想時に手に入る情報のみ）。
"""
import re, os, sys
from collections import Counter, defaultdict
import monogatari as M
import tenkai_ooi as T

MEETS = {
 "06": ["0413","0414","0415","0416","0417"],
 "07": ["0427","0428","0429","0430","0501"],
 "08": ["0518","0519","0520","0521","0522"],
 "09": ["0608","0609","0610","0611","0612"],
 "10": ["0629","0630","0701","0702","0703"],
}

def result(rid):
    """{umaban:(chaku,ninki)} と baba を返す。通過は使わない。"""
    f = os.path.join(M.ARC, f"kekka_{rid}.html")
    M._get(f"{M.BASE}/chihou/seiseki/{rid}", f)
    h = open(f, encoding="utf-8", errors="replace").read()
    mb = re.search(r"(?:晴|曇|雨|小雨|雪|雷)・(不良|稍重|重|良)", h)
    baba = mb.group(1) if mb else None
    res = {}
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        row = m.group(1)
        if 'class="umaban"' not in row: continue
        tds = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(tds) < 16 or not tds or not re.match(r"^\d+$", tds[0]): continue
        try:
            chaku = int(tds[0]); ub = int(tds[4]); nk = int(tds[15])
        except (ValueError, IndexError):
            continue
        res[ub] = (chaku, nk)
    return res, baba

def analyze_ok(rid):
    try:
        horses, front, pace, read = T.analyze(rid)
    except Exception:
        return None
    if not horses: return None
    return horses, front, pace

# ---- 軸候補ルール ----
def jiku_rules(horses, pace, res):
    """各ルールの軸馬(馬番)を返す。人気はresから引く。"""
    # 人気付き（予想時odds代替）
    for h in horses:
        h["nk"] = res.get(h["ub"], (99, 99))[1]
    ranked = sorted(horses, key=lambda x: x["nk"])
    front_slot = [h for h in horses if h["role"] in ("逃げ", "先行", "好位")]
    out = {}
    # A: 市場1番人気
    out["A_人気1"] = ranked[0]["ub"] if ranked else None
    # B: 好位・前スロットで人気最上位（展開フィルタ本命）
    fs = sorted(front_slot, key=lambda x: x["nk"])
    out["B_前好位×人気上位"] = fs[0]["ub"] if fs else None
    # C: 最も前（avg1最小）の馬
    out["C_最前avg1"] = min(horses, key=lambda x: x["avg1"])["ub"] if horses else None
    return out

# ---- 穴候補ルール（単人気>=5 を狙う） ----
def ana_rules(horses, pace, res):
    for h in horses:
        h["nk"] = res.get(h["ub"], (99, 99))[1]
    ura = [h for h in horses if h["nk"] >= 5 and h["nk"] < 99]
    front_slot = [h for h in ura if h["role"] in ("逃げ", "先行", "好位")]
    out = {}
    # E基準: 人気薄の中で市場最上位(=人気5,6番手)＝素の人気薄
    ura_s = sorted(ura, key=lambda x: x["nk"])
    out["E基準_人気薄筆頭"] = ura_s[0]["ub"] if ura_s else None
    # D: 人気薄×好位前 で最も前
    fs = sorted(front_slot, key=lambda x: x["avg1"])
    out["D_人気薄×前好位"] = fs[0]["ub"] if fs else None
    # F: スロー時は人気薄の逃げ/先行、ハイ時は人気薄の好位
    if pace in ("スロー(単騎)", "ドスロー"):
        cand = [h for h in ura if h["role"] in ("逃げ", "先行")]
    else:
        cand = [h for h in ura if h["role"] == "好位"]
    cand = sorted(cand, key=lambda x: x["avg1"])
    out["F_ペース連動人気薄"] = cand[0]["ub"] if cand else None
    return out

def run(kais):
    jiku_hit = defaultdict(lambda: [0, 0, 0])   # rule -> [races, 3着内, 勝ち]
    ana_hit = defaultdict(lambda: [0, 0, 0])
    ana_nk = defaultdict(list)                    # rule -> list of nk of hits
    nr = 0
    for kai in kais:
        for mmdd in MEETS[kai]:
            head = f"2026{kai}10{MEETS[kai].index(mmdd)+1:02d}"
            for rr in range(1, 13):
                rid = f"{head}{rr:02d}{mmdd}"
                a = analyze_ok(rid)
                if not a: continue
                horses, front, pace = a
                res, baba = result(rid)
                if len(res) < 5: continue
                nr += 1
                jr = jiku_rules(horses, pace, res)
                for rule, ub in jr.items():
                    if ub is None: continue
                    chaku = res.get(ub, (99, 99))[0]
                    jiku_hit[rule][0] += 1
                    if chaku <= 3: jiku_hit[rule][1] += 1
                    if chaku == 1: jiku_hit[rule][2] += 1
                ar = ana_rules(horses, pace, res)
                for rule, ub in ar.items():
                    if ub is None: continue
                    chaku, nk = res.get(ub, (99, 99))
                    ana_hit[rule][0] += 1
                    if chaku <= 3:
                        ana_hit[rule][1] += 1; ana_nk[rule].append(nk)
                    if chaku == 1: ana_hit[rule][2] += 1
    print(f"=== 大井 回{'+'.join(kais)} 軸/穴 検証（{nr}R） ===", flush=True)
    print("【軸ルール】 発走 / 3着内率 / 勝率", flush=True)
    for rule, (n, p3, w) in sorted(jiku_hit.items()):
        if n: print(f"  {rule:16s} {n:3d}R  複{p3}/{n}={p3/n*100:.0f}%  勝{w}/{n}={w/n*100:.0f}%", flush=True)
    print("【穴ルール】(単人気>=5狙い) 対象 / 3着内率 / 勝率 / 的中時平均人気", flush=True)
    for rule, (n, p3, w) in sorted(ana_hit.items()):
        if n:
            anm = sum(ana_nk[rule])/len(ana_nk[rule]) if ana_nk[rule] else 0
            print(f"  {rule:18s} {n:3d}R  複{p3}/{n}={p3/n*100:.0f}%  勝{w}/{n}={w/n*100:.0f}%  的中時平均{anm:.1f}人気", flush=True)

if __name__ == "__main__":
    run(sys.argv[1:] or ["06","07","08","09","10"])
