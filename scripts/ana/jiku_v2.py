"""軸/穴の本命：展開は"単独フィルタ"でなく"市場との食い違い"で使う。
仮説: 1番人気が【展開不適(=差し/後方/中団)】の時は信頼を落とすべき。
     その時こそ、好位・前の人気薄(穴)が浮上する。
出力:
 1) 1番人気の複勝率/勝率を 役割(適=逃先好 / 不適=差中後) × ペース で分解
 2) 1番人気=不適 の時、好位・前の人気2-3番手 or 人気薄が来るか（軸差し替え・穴）
"""
import re, os, sys
from collections import defaultdict
import monogatari as M
import tenkai_ooi as T
import jiku_ana as J

MEETS = J.MEETS
FIT = ("逃げ", "先行", "好位")

def run(kais):
    fav_by_fit = defaultdict(lambda: [0, 0, 0])       # 適/不適 -> [n, 複, 勝]
    fav_by_fitpace = defaultdict(lambda: [0, 0, 0])   # (fit,pace)
    # 本命が不適の時の代替軸: 好位前の人気最上位(2-4番手想定)
    alt_when_unfit = [0, 0, 0]                          # n,複,勝  (代替軸)
    fav_when_unfit = [0, 0, 0]                          # 同レースの本命成績（比較用）
    # 本命が適の時の穴: 好位前人気薄
    ana_favfit = [0, 0]; ana_favunfit = [0, 0]         # [対象, 複] 好位前人気>=5
    nr = 0
    for kai in kais:
        for mmdd in MEETS[kai]:
            head = f"2026{kai}10{MEETS[kai].index(mmdd)+1:02d}"
            for rr in range(1, 13):
                rid = f"{head}{rr:02d}{mmdd}"
                a = J.analyze_ok(rid)
                if not a: continue
                horses, front, pace = a
                res, baba = J.result(rid)
                if len(res) < 6: continue
                role = {h["ub"]: h["role"] for h in horses}
                nk = {ub: n for ub, (c, n) in res.items()}
                chk = {ub: c for ub, (c, n) in res.items()}
                fav_ub = next((ub for ub, n in nk.items() if n == 1), None)
                if fav_ub is None or fav_ub not in role: continue
                nr += 1
                fr = role[fav_ub]
                fit = "適" if fr in FIT else "不適"
                fc = chk[fav_ub]
                fav_by_fit[fit][0] += 1; fav_by_fit[fit][1] += fc <= 3; fav_by_fit[fit][2] += fc == 1
                fav_by_fitpace[(fit, pace)][0] += 1
                fav_by_fitpace[(fit, pace)][1] += fc <= 3
                fav_by_fitpace[(fit, pace)][2] += fc == 1
                if fit == "不適":
                    # 代替軸 = 好位前で人気最上位(本命除く)
                    cand = [(nk[h["ub"]], h["ub"]) for h in horses
                            if h["role"] in FIT and h["ub"] in nk and h["ub"] != fav_ub]
                    cand.sort()
                    if cand:
                        aub = cand[0][1]; ac = chk[aub]
                        alt_when_unfit[0] += 1; alt_when_unfit[1] += ac <= 3; alt_when_unfit[2] += ac == 1
                        fav_when_unfit[0] += 1; fav_when_unfit[1] += fc <= 3; fav_when_unfit[2] += fc == 1
                # 穴(好位前×人気>=5)を本命の適/不適で層別
                ura = [h for h in horses if h["role"] in FIT and h["ub"] in nk and nk[h["ub"]] >= 5]
                ura.sort(key=lambda x: x["avg1"])
                if ura:
                    u = ura[0]["ub"]; hit = chk[u] <= 3
                    if fit == "適": ana_favfit[0] += 1; ana_favfit[1] += hit
                    else: ana_favunfit[0] += 1; ana_favunfit[1] += hit
    def pct(a, b): return f"{a}/{b}={a/b*100:.0f}%" if b else "-"
    print(f"=== 軸/穴 v2：市場×展開の食い違い（{nr}R） ===", flush=True)
    print("① 1番人気の成績を 展開適性 で分解:", flush=True)
    for fit in ["適", "不適"]:
        n, p3, w = fav_by_fit[fit]
        print(f"   本命が展開【{fit}】: {n}R  複{pct(p3,n)}  勝{pct(w,n)}", flush=True)
    print("② さらにペース別（本命の適/不適 × ペース）:", flush=True)
    for (fit, pace), (n, p3, w) in sorted(fav_by_fitpace.items()):
        if n >= 5: print(f"   {fit}×{pace:10s}: {n:3d}R 複{pct(p3,n)} 勝{pct(w,n)}", flush=True)
    print("③ 本命が【不適】の時、好位前の人気上位に軸を差し替えると:", flush=True)
    print(f"   代替軸(好位前・人気上位): {alt_when_unfit[0]}R 複{pct(alt_when_unfit[1],alt_when_unfit[0])} 勝{pct(alt_when_unfit[2],alt_when_unfit[0])}", flush=True)
    print(f"   （同レースの本命）      : {fav_when_unfit[0]}R 複{pct(fav_when_unfit[1],fav_when_unfit[0])} 勝{pct(fav_when_unfit[2],fav_when_unfit[0])}", flush=True)
    print("④ 穴(好位前×人気>=5筆頭) を本命の適/不適で層別:", flush=True)
    print(f"   本命=適 の時: {ana_favfit[0]}R 複{pct(ana_favfit[1],ana_favfit[0])}", flush=True)
    print(f"   本命=不適の時: {ana_favunfit[0]}R 複{pct(ana_favunfit[1],ana_favunfit[0])}", flush=True)

if __name__ == "__main__":
    run(sys.argv[1:] or ["06","07","08","09","10"])
