"""大井 展開予想（実通過ベース／cookie開通版）。
各馬のDBページから近5走の通過(tuka)を取り、脚質(1角平均+逃げ回数)を判定→
レースの逃げ争い頭数でペース→良馬場大井(差し天国)の前提で前残り/差しを読む。
1馬1フェッチ(DBページ)。標準ライブラリ+monogatari(race_danwa/_get)。
"""
import re, os, sys
import monogatari as M

def kyakushitsu(cd):
    """DBページの近5走通過→ {avg1, nige, seqs}。"""
    h = open(M._get(f"{M.BASE}/db/uma/{cd}/kanzen", os.path.join(M.ARC, f"umaNEW_{cd}.html")),
             encoding="utf-8", errors="replace").read()
    seqs = []
    for t in re.findall(r'<ul class="tuka">(.*?)</ul>', h, re.S):
        digs = re.findall(r">(\d+)<", t)
        if digs: seqs.append([int(x) for x in digs])
        if len(seqs) >= 5: break
    if not seqs: return None
    firsts = [s[0] for s in seqs]
    avg1 = sum(firsts) / len(firsts)
    nige = sum(1 for s in seqs if s[0] == 1)         # 早い段階で先頭
    senko = sum(1 for s in seqs if s[0] <= 3)
    return {"avg1": avg1, "nige": nige, "senko": senko, "n": len(seqs), "seqs": seqs}

def role(avg1):
    if avg1 <= 1.8: return "逃げ"
    if avg1 <= 3.0: return "先行"
    if avg1 <= 5.0: return "好位"
    if avg1 <= 8.0: return "中団"
    return "後方"

def analyze(rid):
    d = M.race_danwa(rid)
    horses = []
    for cd, info in d.items():
        ub = info.get("umaban")
        if ub is None: continue
        k = kyakushitsu(cd)
        if not k:
            horses.append({"ub": ub, "name": info["name"], "avg1": 9.9, "nige": 0, "senko": 0, "role": "?"})
        else:
            horses.append({"ub": ub, "name": info["name"], **k, "role": role(k["avg1"])})
    horses.sort(key=lambda x: x["avg1"])
    # 逃げ争い＝1角平均2.0以下 or 近走で複数回ハナ
    front = [h for h in horses if h["avg1"] <= 2.3 or h.get("nige", 0) >= 2]
    nf = len(front)
    pace = "超ハイ" if nf >= 4 else "ハイ" if nf >= 3 else "ミドル" if nf == 2 else "スロー(単騎)" if nf == 1 else "ドスロー"
    # 良馬場大井(差し天国)の読み
    if nf >= 3:  read = "前傾ハイ→前崩れ＝【差し・追い込み】が本線"
    elif nf == 2: read = "ミドル→上がり勝負＝【差し／好位差し】、前2頭は共倒れ注意"
    elif nf == 1: read = "単騎逃げ→【前残り】警戒、ただし大井良は差しも届く"
    else:        read = "総controlスロー→【前・好位】有利、瞬発力上位を"
    return horses, front, pace, read

if __name__ == "__main__":
    rid = sys.argv[1]
    horses, front, pace, read = analyze(rid)
    print(f"=== {rid} 展開予想 === 逃げ争い{len(front)}頭 ペース【{pace}】")
    print(f"読み: {read}")
    for h in horses:
        fi = "★前" if h in front else ""
        print(f"  {h['role']:>2} | {h['ub']:2}番 {h['name']} 1角avg{h['avg1']:.1f} 逃{h.get('nige',0)} {fi}")
