"""1頭ずつ、近5走の「落ち込み」を並べて見る ── 調子が上がっているかを目で確かめる道具。

  python3 choushi.py <馬名の一部>                 # 第11回大井の出走馬から引く
  python3 choushi.py --card <card.json> <馬名>    # 出馬表（syutuba.py の出力）から引く
  python3 choushi.py --card <card.json> --R 7     # その鞍の全頭を一覧（1行ずつ）
  python3 choushi.py --card <card.json> --all     # 全鞍を一覧

── 何を測っているか

  **減速率 ＝ 上がり3Fの1Fあたり − 自前半の1Fあたり（秒／200m）**

  自前半 ＝ 走破タイム − 上がり3F。楽天は前半を出さないが引き算で出る。
  この値が小さいほど「落ちていない」。

  競走馬はスタート後 200〜400m で最高速に達し、あとはゴールまで減速し続ける。
  36鞍を調べて、**最後の1ハロンが最速だったレースは1つもなかった**（平均 +1.65秒）。
  だから速さとは「どれだけ加速したか」ではなく「どれだけ落ちなかったか」。

── 水準で補正している（suijun.json）

  減速率は距離と馬場で大きく変わる。同じ1200mでも
  **良 +0.767 に対して不良は +1.100** と、0.33秒ぶん余計に落ちる。
  補正しないと「馬場が渋かっただけ」を「調子が落ちた」と読み違える。

  水準表は第11回大井（10/26-28）の出走423頭・近5走1,588走の中央値。
  セルが薄いとき（8走未満）は距離だけの中央値で代用し、それも無ければ `水準なし`。

── ★ 分かっていること ── 「上がってきている」は測れない

  423頭で、傾き（古い走→新しい走の変化）を5等分して今開催の成績を見た。

    いちばん上昇した群  3着内 12.9%  ← いちばん悪い
    第2群               3着内 33.3%
    いちばん悪化した群  3着内 22.4%

  **順番になっていない。**5走しかないので、いちばん古い1走が外れ値だと
  傾きがそれだけで決まる。減速率そのもののばらつき（SD約0.4）に対して
  5点では傾きを推定できない。

  一方「直近1走の水準」は弱く効いた ── 良い順に 30.6% / 22.2% / 27.0% / 20.6% / 16.7%。

  **つまり「良くなってきている」は数字で切れない。「いま良い」は少し切れる。**
  このツールは順位づけのためではなく、**並べて目で見るため**に置いてある。
  距離と馬場を各行に出してあるので、「距離が変わっただけ」と
  「本当に変わった」を自分の目で分けること。
"""
import sys, json, os, statistics as st, unicodedata as ud

HERE = os.path.dirname(os.path.abspath(__file__))
SUI = json.load(open(os.path.join(HERE, "suijun.json")))
KAI = os.path.join(HERE, "ooi11_kaisai.json")
W = 44          # 目盛りの幅（文字）
SPAN = 1.2      # 左端 −1.2秒 〜 右端 +1.2秒


def wd(s):
    return sum(2 if ud.east_asian_width(c) in "FW" else 1 for c in s)


def w(s, n):
    """表示幅 n にそろえる。はみ出すぶんは切る（棒の位置をずらさないため）"""
    while wd(s) > n:
        s = s[:-1]
    return s + " " * max(0, n - wd(s))


def dec(p):
    """減速率。前半も上がりも無い走は測れない"""
    if not (p.get("agari") and p.get("zen")):
        return None
    f = (p["dist"] - 600) / 200
    return None if f <= 0 else p["agari"] / 3 - p["zen"] / f


def level(p):
    """水準との差。マイナス＝その条件の平均より落ちていない"""
    d = dec(p)
    if d is None:
        return None, None
    m = SUI["cell"].get("%d|%s" % (p["dist"], p["baba"]))
    src = "距離×馬場"
    if m is None:
        m = SUI["dist"].get(str(p["dist"]))
        src = "距離のみ"
    return (None, None) if m is None else (d - m, src)


def axis():
    mid = W // 2
    s = ["─"] * W
    s[mid] = "┼"
    return "".join(s)


def plot(v):
    """−SPAN〜+SPAN を W 文字に写して ● を置く"""
    mid = W // 2
    i = mid + int(round(v / SPAN * mid))
    i = max(0, min(W - 1, i))
    s = [" "] * W
    s[mid] = "│"
    s[i] = "●"
    return "".join(s)


def one(name, past, now=None):
    print("\n■ %s" % name)
    if now:
        print("   %s" % now)
    pad = " " * 48
    print(pad + "落ちていない ←       ┼       → 落ちている")
    print(pad + axis())
    vs = []
    for p in reversed(past):          # 古い順に並べる
        lv, src = level(p)
        head = "%s %s %s %4dm %2d頭 %2d人 %2d着 %+.1f" % (
            p["date"], p["venue"], p["baba"], p["dist"], p["n"], p["nk"],
            p["chaku"], p["sa"])
        if lv is None:
            print("   %s  水準なし" % w(head, 44))
            continue
        vs.append(lv)
        mark = "" if src == "距離×馬場" else " ※距離のみ"
        print("   %s %s %+5.2f%s" % (w(head, 44), plot(lv), lv, mark))
        print("   %s前半%s + 上がり%s = %s　通過 %s　体%s" % (
            " " * 6, p.get("zen"), p.get("agari"), p.get("t"),
            "-".join(str(x) for x in p["tsuka"]), p.get("w")))
    if len(vs) >= 2:
        n = len(vs)
        xs = list(range(n)); mx = st.mean(xs); my = st.mean(vs)
        dd = sum((x - mx) ** 2 for x in xs)
        sl = sum((x - mx) * (y - my) for x, y in zip(xs, vs)) / dd if dd else 0
        print("\n   直近の水準 %+.2f ／ 傾き %+.3f（マイナス＝落ち込みが減ってきている）／ %d走" % (
            vs[-1], sl, n))
        print("   ★ 傾きは5走では当てにならない（docstring参照）。直近の水準のほうを見ること。")
    elif vs:
        print("\n   直近の水準 %+.2f ／ 1走しか測れない" % vs[-1])
    else:
        print("\n   測れる走がない（前半か上がりが欠けている）")


def brief(nm, past, extra=""):
    vs = [level(p)[0] for p in past]
    vs = [v for v in vs if v is not None]
    if not vs:
        return "   %s 測れない %s" % (w(nm, 16), extra)
    sl = ""
    if len(vs) >= 3:
        r = list(reversed(vs)); n = len(r); xs = list(range(n))
        mx = st.mean(xs); my = st.mean(r)
        dd = sum((x - mx) ** 2 for x in xs)
        sl = "傾き%+.3f" % (sum((x - mx) * (y - my) for x, y in zip(xs, r)) / dd) if dd else ""
    return "   %s 直近%+5.2f  %s %-12s %s" % (
        w(nm, 16), vs[0], plot(vs[0]), sl, extra)


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    if "--card" in a:
        D = json.load(open(a[a.index("--card") + 1]))
        if "--R" in a or "--all" in a:
            only = None if "--all" in a else [int(a[a.index("--R") + 1])]
            for k in sorted(D, key=int):
                v = D[k]
                if only and v["R"] not in only:
                    continue
                print("\n%2dR ダ%dm %2d頭  %s" % (
                    v["R"], v["dist"], len(v["horses"]), (v.get("cls") or "")[:20]))
                print(" " * 31 + "落ちていない ←   ┼   → 落ちている")
                print(" " * 31 + axis())
                rows = []
                for h in v["horses"]:
                    rows.append((h, brief("%2d %s" % (h["ub"], h["name"]),
                                          h.get("past") or [])))
                for h, s in rows:
                    print(s)
            return
        q = [x for x in a if not x.startswith("--") and not x.endswith(".json")]
        q = q[0] if q else ""
        for k in sorted(D, key=int):
            v = D[k]
            for h in v["horses"]:
                if q in h["name"]:
                    one(h["name"], h.get("past") or [],
                        "本日 %2dR ダ%dm %d頭 %d番%s枠" % (
                            v["R"], v["dist"], len(v["horses"]), h["ub"], h.get("waku") or "?"))
        return
    H = json.load(open(KAI))
    q = a[0]
    hit = [e for nm, e in H.items() if q in nm]
    if not hit:
        print("%s に当たる馬がいません" % q); return
    for e in sorted(hit, key=lambda e: e["name"]):
        r = e["kaisai"][0]
        one(e["name"], e["past5"],
            "今開催 %s %2dR ダ%dm %s %d頭 → %s着 %s人気 4角%s 上%s %s%s" % (
                r["date"][5:], r["R"], r["dist"], r["baba"], r["n"],
                r["chaku"], r["nk"], r.get("c4"), r.get("agari"),
                r.get("w"), r.get("dw") or ""))


if __name__ == "__main__":
    main()
