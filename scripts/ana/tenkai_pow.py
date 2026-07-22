"""展開×血統パワー軸 統合ビュー（大井）。
tenkai_ooi.analyze で隊列/ペース → daikei.power で各馬のパワー軸(パ/ス/軽)を重ねる。
今日=タフ・パワー馬場の前提で「前が止まりにくい/パワー差し有利」を補正して読む。
使い方: python3 tenkai_pow.py <rid> [pace_mode]   pace_mode: power(既定=タフ馬場)/normal(差し天国)
"""
import sys, monogatari as M, pedigree_line as P, daikei as D, tenkai_ooi as T

def run(rid, mode="power"):
    horses, front, pace, read = T.analyze(rid)
    ped = P.sires(rid)
    d = M.race_danwa(rid)
    ub2cd = {info["umaban"]: cd for cd, info in d.items() if info.get("umaban")}
    for h in horses:
        cd = ub2cd.get(h["ub"]); pi = ped.get(cd, {}) if cd else {}
        h["sire"] = pi.get("sire"); h["gsire"] = pi.get("gsire")
        h["pow"] = D.power(h["sire"], h["gsire"]); h["ko"] = D.classify(h["sire"], h["gsire"])["ko"]
    fp = sum(1 for h in front if h["pow"] == "パ")
    print(f"=== {rid} 6R展開×血統 === 逃げ争い{len(front)}頭 ペース【{pace}】 (ハナ争いのパワー血統{fp}/{len(front)})")
    if mode == "power":
        if len(front) >= 3 and fp >= 2:
            print("読み(タフ馬場補正): 前3頭が全員パワー血統寄り→"
                  "『全部潰れる差し天国』にはなりにくい。先行パワーの粘り＋好位パワー差しが本線。軽い切れ型は割引")
        elif len(front) >= 3:
            print("読み: 前傾ハイだがハナ争いに軽い型混在→パワー血統の先行/差しに絞る")
        else:
            print(f"読み(タフ馬場): {read} ※今日はパワー型を上位に")
    else:
        print(f"読み(標準): {read}")
    PW = {"パ": "◎パワー", "ス": "△スピード", "軽": "×軽い", "中": "・中間"}
    for h in horses:
        fi = "★前" if h in front else ""
        print(f"  {h['role']:>2}|{h['ub']:2}番 {h['name']:10} 1角{h['avg1']:.1f} "
              f"父{str(h['sire'] or '?'):12}{h['ko']:8} {PW.get(h['pow'],'?')} {fi}")

if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "power")
