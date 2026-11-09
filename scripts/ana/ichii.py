"""鞍内の「上がり1位」になれる馬を探す ── 2026-10-27 大井で出た形。

  python3 ichii.py <card.json> [R...] [--ana] [--n 4]

card.json は syutuba.py が吐く楽天の出馬表（過去5走・枠・走破タイムつき）。

── なぜ上がり1位なのか（2026-10-27 大井・全12鞍 不良）

  **鞍内の上がり1位が、12鞍すべて3着内。うち9勝。**

    1R 1着 / 2R 1着 / 3R 1着 / 4R 1着 / 5R 1着 / 6R 1着(10人気)
    7R 1着 / 8R 2着 / 9R 1着 / 10R 1着 / 11R 2着(9人気) / 12R 3着

  3着内36頭のうち上がり3位以内は26頭（72.2%）でルール7の基準には届かない。
  **信号は「3位以内」ではなく「1位ちょうど」に集中していた。**
  厚く買う形ではなく、1頭当てにいく形。

  そして **4角7番手以降から3着内に来た5頭は、全員がその鞍の上がり1位。**
  後ろから届いたのではなく、鞍内で最速の脚を使えた馬だけが届いた。

── 上がり1位が「前から出るか後ろから出るか」はラップで決まる

  最速ハロン → 最終ハロンの落差で12鞍中11鞍が分かれた。

    落差 +1.8以上（5鞍） … 上がり1位は全部 4角5番手以降
    落差 +1.4以下（7鞍） … 6鞍が 4角1〜4番手

  事前に読む材料は **2F目が11秒台に入るか**（大井のスタート後の加速区間）。
  11秒台＝前が持たない。12秒台＝前が残る。
  ★ 例外は「緩急が2回ある」長距離（10/27 11R 2000m）。落差が小さくても後ろが届く。

── ★ 距離帯をまたがない（CLAUDE.md ルール2）

  上がりは今日と同じ距離帯の走だけを使う。1400m戦なら1200〜1600m。
  **800mや1000mの上がりを1400mに持ち込むと逃げ馬が1位になる。**
  距離帯の実績がない馬は上がりを使わない（除外ではなく「測れない」扱い）。

── ★ 手で切らない（10/26・10/27 の反省）

  2日続けて、**ツールの出力より、私が手で直したほうが悪かった。**
  10/27 は 機械の13頭 3着内46.2% ＞ 手で選んだ8頭 37.5%、
  そして **私が「外す」に落とした7頭が57.1%** で最良だった。

  この日の穴2頭（6R⑫ 10人気1着・11R⑫ 9人気2着）は両方とも私が手で切った馬。
  却下理由はどちらも**前走以前の古い馬体重**だった。

    馬体重で切らない … 当日に取り直すまで判断しない（ルール3・4）
    人気で切らない   … 「人気するから妙味なし」は買い方の話。選ぶ段階でやらない
    履歴の薄さで切らない … ルール6

── --ana（穴モード）

  人気が落ちる材料を持ったまま、鞍内の上がり上位にいる馬だけを出す。
  10/26・10/27 に二桁人気で来た馬は全部この形だった。
"""
import sys, json, statistics as st, unicodedata as ud


def w(s, n):
    l = sum(2 if ud.east_asian_width(c) in "FW" else 1 for c in s)
    return s + " " * max(0, n - l)


def band(d):
    """今日の距離から、上がりを借りてよい距離帯"""
    if d <= 1000: return (0, 1100)
    if d <= 1200: return (1000, 1400)
    if d <= 1400: return (1200, 1600)
    if d <= 1600: return (1400, 1800)
    if d <= 1800: return (1600, 2000)
    return (1800, 2600)


def prof(h, dist):
    past = h.get("past") or []
    lo, hi = band(dist)
    bb = [p for p in past if p.get("agari") and lo <= p["dist"] <= hi]
    c4 = [p["c4"] for p in past if p.get("c4")]
    if not (bb and c4):
        return None
    best = min(bb, key=lambda p: p["agari"])
    p0 = past[0]
    return {"best": best["agari"], "mean": st.mean(p["agari"] for p in bb),
            "n": len(bb), "bc4": best.get("c4"), "bbaba": best["baba"],
            "bdist": best["dist"], "av": st.mean(c4),
            "pnk": p0["nk"], "pchaku": p0["chaku"], "pn": p0["n"],
            "w": p0.get("w"), "dd": dist - p0["dist"]}


def run(D, only=None, ana=False, top=4):
    for k in sorted(D, key=int):
        v = D[k]
        if only and v["R"] not in only:
            continue
        d = v["dist"] or 0
        rows = []
        for h in v["horses"]:
            z = prof(h, d)
            if z:
                rows.append((z["best"], h, z))
        rows.sort(key=lambda r: r[0])
        ws = [h["past"][0]["w"] for h in v["horses"] if h.get("past") and h["past"][0].get("w")]
        mw = st.mean(ws) if len(ws) >= 5 else None
        print("\n%2dR ダ%dm %2d頭  %s" % (v["R"], d, len(v["horses"]), (v.get("cls") or "")[:22]))
        if not rows:
            print("    同じ距離帯の上がりを持つ馬がいない ── この鞍は測れない")
            continue
        out = []
        for i, (b, h, z) in enumerate(rows, 1):
            if ana:
                # 人気が落ちる材料：前走が負けている／人気薄だった
                ochiru = z["pchaku"] >= 5 or z["pnk"] >= 6
                if i > top + 2 or not ochiru:
                    continue
            elif i > top:
                continue
            out.append((i, h, z, mw))
        if not out:
            print("    該当なし")
            continue
        for i, h, z, mw in out:
            dw = (z["w"] - mw) if (z["w"] and mw) else None
            print("  上がり%d位 %2d %s %s枠  最速%.1f（4角%s・%s%dm） 平均%.1f/%d走" % (
                i, h["ub"], w(h["name"], 16), h.get("waku") or "?",
                z["best"], z["bc4"], z["bbaba"], z["bdist"], z["mean"], z["n"]))
            print("            普段4角%.1f番手  前走%d人気%d着/%d頭  距離%+dm  前走体重%s%s" % (
                z["av"], z["pnk"], z["pchaku"], z["pn"], z["dd"], z["w"] or "?",
                ("（平均%+.0f）" % dw) if dw is not None else ""))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    D = json.load(open(a[0]))
    ana = "--ana" in a
    top = int(a[a.index("--n") + 1]) if "--n" in a else 4
    skip = {a.index("--n") + 1} if "--n" in a else set()
    only = [int(x) for i, x in enumerate(a) if i and i not in skip and x.isdigit()]
    print(__doc__.split("──")[0].strip())
    print("  鞍内で上がり%d位まで%s／ 上がりは同じ距離帯の走だけ" % (
        top, "・前走が負けている馬だけ（穴）" if ana else ""))
    run(D, only or None, ana, top)


if __name__ == "__main__":
    main()
