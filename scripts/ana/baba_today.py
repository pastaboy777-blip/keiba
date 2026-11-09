"""その日の馬場を「同じ馬の過去走」と比べて測る ── クラスの影響を受けない物差し。

  python3 baba_today.py <card.json> <base16> [--R 1 3 5]

── ★ なぜ toki.json と比べてはいけないか（2026-11-09 川崎で踏んだ）

  toki.json は場×距離×馬場の**全クラスの中央値**。
  11/9 川崎の 1R（3歳3）・2R・3R（2歳戦）を toki.json と比べて
  「今日は年間の重より0.7〜1.2秒遅い馬場」と書いたが、**これは誤り**。
  下級条件が遅いのは当たり前で、馬場のせいではない。

  同じ馬の過去走と比べ直すと逆だった。
    1R 差の中央値 +1.2秒（ただし使える馬4頭、うち1頭は251日ぶりの1走比較）
    3R 差の中央値 **−0.8秒**（8頭中7頭が自分より速い）
  3Rは馬場がむしろ速い。toki.json で見ていたら真逆に読んでいた。

  **クラスを揃えずに水準と比べない。馬で揃えれば揃う。**

── 使い方の注意

  1. 同じ場・同じ距離の過去走だけを使う（場が変われば比べられない）
  2. **n が少ない馬は外れ値になる。**上の③ヴィヒタは251日ぶりの1走比較で+6.5。
     中央値を取るのはそのため。頭数が4頭を切る鞍の数字は信用しない
  3. 前走からの間隔が長い馬・距離を替えた馬は本人比でも遅くなる
"""
import sys, os, re, json, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harvest as H

MIN_N = 4       # これ未満の頭数しか比べられない鞍は、数字を出しても当てにしない


def sec(s):
    m = re.match(r"(?:(\d+):)?([\d.]+)$", s)
    return (int(m.group(1) or 0) * 60 + float(m.group(2))) if m else None


def result(base16, R):
    t = H.flat(H.rk("https://keiba.rakuten.co.jp/race_performance/list/RACEID/%s%02d" % (base16, R)))
    i = t.find("全着順")
    if i < 0 or "お待ちください" in t[i:i + 60]:
        return None
    seg = re.sub(r"\s+", " ", t[i:i + 1800])
    out = {}
    for m in re.finditer(r"(\d{1,2}) (\d{1,2}) (\d{1,2}) ([ァ-ヶー]{3,}) [牡牝セ]\d+ ?/\S+ "
                         r"[\d.]+ \d{3}(?: [-+±]\d+)? \S+ \(\S+\) ([\d:.]+)", seg):
        out[m.group(4)] = (int(m.group(1)), sec(m.group(5)))
    return out


def run(card, base16, rs=None):
    C = json.load(open(card))
    ven = {"ooi": "大井", "fun": "船橋", "ura": "浦和", "kaw": "川崎"}.get(os.path.basename(card)[:3], "川崎")
    allds = []
    for k in sorted(C, key=int):
        v = C[k]
        if rs and v["R"] not in rs:
            continue
        res = result(base16, v["R"])
        if not res:
            print("%2dR まだ" % v["R"]); continue
        ds = []
        rows = []
        for h in v["horses"]:
            r = res.get(h["name"])
            if not r:
                continue
            past = [p["t"] for p in (h.get("past") or [])
                    if p.get("t") and p["dist"] == v["dist"] and p.get("venue") == ven]
            if not past:
                rows.append((r[0], h, r[1], None, 0)); continue
            d = r[1] - st.median(past)
            ds.append(d); rows.append((r[0], h, r[1], d, len(past)))
        print("\n%2dR ダ%dm" % (v["R"], v["dist"]))
        for ch, h, t_, d, n in sorted(rows):
            if d is None:
                print("   %2d着 %2d %-16s %5.1f  同条件の過去走なし" % (ch, h["ub"], h["name"], t_))
            else:
                print("   %2d着 %2d %-16s %5.1f  本人比 %+5.1f (%d走)" % (ch, h["ub"], h["name"], t_, d, n))
        if ds:
            m = st.median(ds)
            allds += ds
            print("   → 本人比の中央値 %+.1f秒（%d頭）%s" % (
                m, len(ds), "" if len(ds) >= MIN_N else "  ※頭数が少なく当てにならない"))
    if allds:
        print("\n本日ここまで … 本人比の中央値 %+.1f秒（のべ%d頭）" % (st.median(allds), len(allds)))
        print("   マイナスなら馬場は速い、プラスなら遅い。")


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__); return
    rs = None
    if "--R" in a:
        i = a.index("--R")
        rs = [int(x) for x in a[i + 1:] if x.isdigit()]
        a = a[:i]
    run(a[0], a[1], rs)


if __name__ == "__main__":
    main()
