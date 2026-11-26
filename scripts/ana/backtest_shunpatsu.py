"""瞬発力スコア バックテスト（中央・上がり代理）。
各レースで全頭の事前瞬発力スコア(対象除外)を計算し、結果3着内と照合。
測定: 瞬発力トップ3が3着内に来る率 / 人気薄(6+)×瞬発力上位の3着内率 vs 各ベースライン。
標準ライブラリ + shunpatsu + jra_bias。重いのでレース集合を絞って実行。
"""
import re, sys
import jra_bias as JB
import shunpatsu as S

def field(rid):
    h = JB.get(rid)
    out = []
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", h, re.S):
        cd = re.search(r"/db/uma/(\d+)", m.group(1))
        if not cd: continue
        c = [re.sub(r"<[^>]+>", " ", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)]
        if len(c) < 15 or not re.match(r"^\d+$", c[0]): continue
        nk = None
        for j in range(6, len(c)):
            if re.match(r"^\d+$", c[j]) and 1 <= int(c[j]) <= 18 and j + 1 < len(c) and re.match(r"^\d+\.\d$", c[j + 1]):
                nk = int(c[j])
        out.append({"umacd": cd.group(1), "chaku": int(c[0]), "nk": nk})
    return out

def run(rids):
    st = {k: [0, 0] for k in ["base", "top3", "baseUP", "upTop"]}
    for rid in rids:
        fs = field(rid)
        if len(fs) < 6: continue
        scored = []
        for r in fs:
            s = S.score(r["umacd"], exclude_rid=rid)
            scored.append((s["score"] if s and s["runs"] >= 2 else -1, r))
        ranked = sorted(scored, key=lambda x: -x[0])
        n = len([1 for sc, _ in scored if sc >= 0])
        if n < 5: continue
        top3ids = {id(r) for sc, r in ranked[:3] if sc >= 0}
        for sc, r in scored:
            if r["chaku"] and r["nk"]:
                st["base"][0] += 1; st["base"][1] += (r["chaku"] <= 3)
                if r["nk"] >= 6:
                    st["baseUP"][0] += 1; st["baseUP"][1] += (r["chaku"] <= 3)
            if id(r) in top3ids:
                st["top3"][0] += 1; st["top3"][1] += (r["chaku"] <= 3)
                if r["nk"] and r["nk"] >= 6:
                    st["upTop"][0] += 1; st["upTop"][1] += (r["chaku"] <= 3)
    b = st["base"][1] / st["base"][0] if st["base"][0] else 0
    bu = st["baseUP"][1] / st["baseUP"][0] if st["baseUP"][0] else 0
    def line(nm, k, base):
        f, h = st[k]
        return f"  {nm}: {h}/{f} ({h/f*100:.0f}%)" + (f" 比{(h/f)/base:.2f}x" if f and base else "")
    print(f"=== 瞬発力バックテスト（{len(rids)}R対象） ===")
    print(f"  全馬ベースライン3着内: {st['base'][1]}/{st['base'][0]} ({b*100:.0f}%)")
    print(line("瞬発力トップ3(全馬)", "top3", b))
    print(f"  人気薄(6+)ベースライン: {st['baseUP'][1]}/{st['baseUP'][0]} ({bu*100:.0f}%)")
    print(line("瞬発力上位×人気薄", "upTop", bu))

if __name__ == "__main__":
    head = "20260203"; day = sys.argv[1] if len(sys.argv) > 1 else "08"
    run([f"{head}{day}{rr:02d}" for rr in range(1, 13)])
