"""隊列・ペース・走破タイム・各馬の前後半3F を、走る前に出す。

  python3 tenkai.py --build                  # 時計の水準表を作る（harvest 全部から）
  python3 tenkai.py <card.json>              # 全鞍
  python3 tenkai.py <card.json> --R 7        # その鞍だけ
  python3 tenkai.py <card.json> --check <res.json>   # 予測と実際を突き合わせる

── 出すもの

  ① 隊列      各馬の「前半速度」（同じ距離帯の走から）で並べた推定順
  ② ペース     先頭に立つ3頭の前半速度から、推定の前3F
  ③ 走破タイム  場×距離×馬場の中央値（toki.json）を、①②でずらす
  ④ 各馬の前後半3F  前半速度・終い速度から1頭ずつ
  ⑤ 見解      ①〜④から言えることだけ

── ★ 前にやって外した形を繰り返さないこと

  11/2 の船橋で「前に行きたい馬の数」から流れを読もうとして外した。
  1200m戦7鞍の前3Fは 36.0〜36.6 で**幅0.6秒しかなく**、
  前に行きたい馬の数（6・5・2・2・2・2・3頭）と相関しなかった。

  **頭数で読まない。速度そのものを足す。**
  ここで出す推定前3Fも、当たるかどうかは --check で確かめてから使うこと。

── ★ 走破タイムを当てても着順は当たらない

  全馬が同じ条件で走るので、速い遅いは全員に同じだけかかる。
  走破タイムの使い道は**馬場の向きを測ること**であって、予想そのものではない。

── ★★ 測った結果（11/2 船橋 12鞍）── ②③は水準に負けた

    前3F    私の推定 誤差0.59秒  ／  水準そのまま 誤差0.43秒
    走破     私の推定 誤差0.77秒  ／  水準そのまま 誤差0.71秒

  **何も考えず「いつもの前3F」と言ったほうが当たる。**

  理由 … 1200m戦7鞍の実際の幅は0.6秒（36.0〜36.6）しかないのに、
         私の推定は1.4秒（36.1〜37.5）振れている。
         相関は+0.29で向きは合うが、振れ幅が過大なので足すと誤差が増える。

  11/2 に「前に行きたい馬の**数**では読めない」と分かったあと、
  **速度を足す形に変えても同じだった。**頭数の問題ではなく、
  船橋1200mのペースがそもそもメンバーで動かない、ということ。

  だから使うのは ① 各馬の前半速度・終い速度と推定隊列 と、
  ② toki.json を**当日の馬場を測る物差し**として使うことだけ。
  **メンバーからペースを推定するのには使わないこと。**
"""
import sys, json, os, glob, statistics as st, unicodedata as ud

HERE = os.path.dirname(os.path.abspath(__file__))
TOKI = os.path.join(HERE, "toki.json")
VEN = {"ooi": "大井", "fun": "船橋", "ura": "浦和", "kaw": "川崎"}


def w(s, n):
    l = sum(2 if ud.east_asian_width(c) in "FW" else 1 for c in s)
    while l > n:
        s = s[:-1]
        l = sum(2 if ud.east_asian_width(c) in "FW" else 1 for c in s)
    return s + " " * max(0, n - l)


def build():
    """場×距離×馬場 ごとの、勝ち時計と前3F・後3F の中央値"""
    cell = {}
    n = 0
    for f in glob.glob(os.path.join(HERE, "harvest", "*_res.json")):
        ven = VEN.get(os.path.basename(f)[:3])
        if not ven:
            continue
        try:
            D = json.load(open(f))
        except Exception:
            continue
        for k in D:
            v = D[k]
            L = v.get("lap") or []
            if not L or not v.get("dist") or not v.get("baba"):
                continue
            full = L[1:] if L[0] < 10 else L
            if len(full) < 4:
                continue
            n += 1
            for key in ("%s|%d|%s" % (ven, v["dist"], v["baba"]), "%s|%d" % (ven, v["dist"])):
                c = cell.setdefault(key, {"t": [], "f3": [], "a3": []})
                c["t"].append(sum(L)); c["f3"].append(sum(full[:3])); c["a3"].append(sum(L[-3:]))
    out = {}
    for k, c in cell.items():
        if len(c["t"]) >= 4:
            out[k] = {"t": round(st.median(c["t"]), 1), "f3": round(st.median(c["f3"]), 1),
                      "a3": round(st.median(c["a3"]), 1), "n": len(c["t"])}
    json.dump(out, open(TOKI, "w"), ensure_ascii=False, indent=0, sort_keys=True)
    print("時計の水準 … %dセル / 元データ %d鞍 → %s" % (len(out), n, TOKI))


def sui(ven, dist, baba=None):
    if not os.path.exists(TOKI):
        return None
    B = json.load(open(TOKI))
    if baba:
        c = B.get("%s|%d|%s" % (ven, dist, baba))
        if c:
            return c
    return B.get("%s|%d" % (ven, dist))


def band(d):
    return (d - 200, d + 200) if d >= 1200 else (0, 1000)


def prof(h, dist):
    """その馬の前半速度・終い速度（同じ距離帯の走だけ）"""
    lo, hi = band(dist)
    e, l, c4 = [], [], []
    for p in (h.get("past") or []):
        if lo <= p["dist"] <= hi and p.get("t") and p.get("agari"):
            e.append((p["dist"] - 600) / (p["t"] - p["agari"]))
            l.append(600 / p["agari"])
        if p.get("c4"):
            c4.append((p["c4"] - 1) / max(1, p["n"] - 1))
    return (st.median(e) if e else None, st.median(l) if l else None,
            st.median(c4) if c4 is not None and c4 else None, len(e))


def race(v, ven):
    dist = v["dist"]
    rows = []
    for h in v["horses"]:
        e, l, c, n = prof(h, dist)
        rows.append({"h": h, "e": e, "l": l, "c4": c, "n": n})
    es = [r["e"] for r in rows if r["e"]]
    if not es:
        return rows, None
    rows.sort(key=lambda r: -(r["e"] or 0))
    top3 = [r["e"] for r in rows[:3] if r["e"]]
    # 推定前3F … 先頭に立つ3頭の前半速度の平均で600mを割る
    f3 = 600 / st.mean(top3) if top3 else None
    b = sui(ven, dist, v.get("baba"))
    est = None
    if b:
        d = (f3 - b["f3"]) if f3 else 0
        # 前半が水準より速ければ後半はそのぶん落ちる（半分だけ戻す、という置き方）
        est = b["t"] + d * 0.5
    return rows, {"f3": f3, "base": b, "est": est}


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    if "--build" in a:
        build(); return
    f = [x for x in a if x.endswith(".json")][0]
    ven = VEN.get(os.path.basename(f)[:3], "船橋")
    R = int(a[a.index("--R") + 1]) if "--R" in a else None
    D = json.load(open(f))
    for k in sorted(D, key=int):
        v = D[k]
        if R and v["R"] != R:
            continue
        rows, p = race(v, ven)
        print("\n%s" % ("=" * 78))
        print("%2dR ダ%dm %d頭 %s" % (v["R"], v["dist"], len(v["horses"]), (v.get("cls") or "")[:18]))
        print("=" * 78)
        if p and p["base"]:
            b = p["base"]
            print("  推定 前3F %.1f（水準 %.1f／%d鞍）  推定 走破 %.1f（水準 %.1f）" % (
                p["f3"], b["f3"], b["n"], p["est"], b["t"]))
            print("  → %s" % ("水準より速い流れ" if p["f3"] < b["f3"] - 0.3 else
                              "水準より遅い流れ" if p["f3"] > b["f3"] + 0.3 else "水準どおりの流れ"))
        print("  推定隊列（前半速度の順）")
        for i, r in enumerate(rows):
            if not r["e"]:
                print("     ―  %2d %s 測れない" % (r["h"]["ub"], w(r["h"]["name"], 14))); continue
            print("    %2d番手 %2d %s 前半%.3f 終い%.3f  前3F%.1f 後3F%.1f  %d走" % (
                i + 1, r["h"]["ub"], w(r["h"]["name"], 14), r["e"], r["l"],
                600 / r["e"], 600 / r["l"], r["n"]))


if __name__ == "__main__":
    main()
