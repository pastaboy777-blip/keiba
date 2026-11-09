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

── ★ 終いは「場・距離の水準との差」で見る（2026-11-10 に直した）

  prof() は上がりの**秒そのもの**を比べていた。南関4場を一つにまとめていたので、
  場がちがう馬を同じ物差しに並べていた。

    浦和800m の後3F水準 35.5秒 ／ 川崎900m の後3F水準 37.8秒 ── **2.3秒ちがう**

  11/10 川崎1R で、⑨モーイーワヒネ（浦和800mで上がり35.2〜37.0）を「終い1位」、
  ⑫ハナサキポプラ（川崎900mで38.4〜38.6）を3位と出した。浦和が速いのは当たり前で、
  **馬の力ではなく場の差**。金沢の件（他場の時計を信じた）と同じ穴を、南関の中で踏んでいた。

  いまは `上がり − その場その距離の後3F中央値 + 場間補正` を返す。**小さいほど速い。**
  返り値の符号が逆になったので、順位を取るときは昇順。

  ★ 場の中央値を引くだけでは足りない。同じ馬が2場を走った記録で測ると、
    引いたあとでも系統的にずれる（浦和−船橋 −0.60秒／川崎−浦和 +0.30秒）。
    「浦和は砂が軽い」というユーザーの指摘が数字に出た。VADJ で川崎に揃える。

── ★ 先頭圏が2頭以上いる鞍は、どちらが引くか読めない（2026-11-09 川崎3Rで踏んだ）

  ①ラリーバックは**5走すべて4角先頭**、⑦ローノンバードは4走すべて先頭。
  両方を「先頭圏」と書いたが、実際の4角は `(4,7),(2,5),3-1,8,6` で
  **①は6番手**だった。⑦が行き、①が引いた。

  過去の位置は「前に行ける」ことしか言わない。**誰が譲るかは言わない。**
  先頭圏（相対0.12以下）が2頭以上いる鞍では、
  「この馬が逃げる」と書かず「先頭を主張するのはこの数頭」に留めること。

── ★ toki.json をクラスの違う鞍に当てない（同じ日に踏んだ）

  toki.json は**全クラスの中央値**。11/9の1R（3歳3）・3R（2歳未勝利）を
  これと比べて「今日は年間の重より遅い馬場」と書いたが誤り。
  同じ馬の過去走と比べ直すと 3R は **−0.8秒**（8頭中7頭が自分より速い）で、
  **馬場はむしろ速かった**。読みが真逆になる。
  当日の馬場は baba_today.py（本人比）で測ること。

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
    """★ ±100mまで。前は ±200m（1200m未満は0〜1000m）にしていたが、これは誤り。

    前半速度は (距離−600) ÷ (タイム−上がり3F)。つまり
    **測っている区間の長さが距離によって変わる**。
      1200m戦 → 600mを測った値
      1400m戦 → 800mを測った値
    短い区間のほうが数字が大きく出るので、並べると1200m組が前に来る。

    11/9 川崎5R（1400m）で実際に踏んだ ── ⑩リコータロス（元が1200m戦）と
    ⑧ドンクベットコール（同じく1200m戦）が1・2番手に並び、推定前3Fが
    36.9 と出た。水準は39.7。**2.8秒の差は馬のせいではなく物差しのせい。**
    川崎に1200mは無いので、1200mの数字は必ず他場から混ざってくる。

    CLAUDE.md ルール2（上がりを距離帯でまたがない）と同じ穴。
    **上がりだけでなく前半速度も距離をまたげない。**"""
    return (d - 100, d + 100)


NANKAN = {"大井", "船橋", "浦和", "川崎"}

# ★ 場間補正 ── 後3Fの水準を引いてもなお残るズレ（川崎を0とする）。
#   同じ馬が2場を走った記録から出した（2026-11-10）。
#     浦和 − 船橋 −0.60秒（360頭） ／ 川崎 − 浦和 +0.30秒（273頭）
#     川崎 − 船橋 −0.25秒（213頭） ／ 大井 − 川崎 +0.05秒（49頭）
#   浦和は「砂が軽い」とユーザーの指摘があり、数字でも裏づけが出た。
#   **場の中央値を引くだけでは足りない。**川崎に揃えるにはここを足す。
#   大井は n が小さい（42〜56頭）ので、この値は当てにしすぎないこと。
VADJ = {"川崎": 0.00, "浦和": +0.30, "船橋": -0.25, "大井": -0.05}


def prof(h, dist):
    """その馬の前半速度・終い速度（同じ距離帯・**南関の走だけ**）

    ★ 2026-11-08 に直した。それまで venue を一度も見ていなかった。

      11/9 川崎1R の ⑦ゼルノードゥスは**5走すべて金沢**で、川崎は初。
      その金沢の時計から前半速度14.953を出し、「先頭圏1頭だけ、楽に行ける形」
      と書いてしまった。**金沢の時計を川崎に換算する物差しは持っていない**
      （harvest は南関4場しか集めていない）。同じ鞍の ③ヴィヒタは
      川崎1400mで4角1番手の実績があり、本当は⑦の単騎ではなかった。

      CLAUDE.md ルール4 は「金沢・佐賀・笠松の馬を0点で沈めるな」だが、
      ここで踏んだのは逆で、**他場の数字をそのまま信じて主役に据えた**。
      沈めないことと、信じることは別。

    返り値の4つめ n は**南関で測れた走の数**。0 なら速度は使えない。
    5つめ ext は他場の走の数（＝0点にしないための目印）。
    位置（c4）は場を問わず使う。どこで走っても前に行く馬は前に行く。
    """
    lo, hi = band(dist)
    B = json.load(open(TOKI)) if os.path.exists(TOKI) else {}
    e, l, c4, ext = [], [], [], 0
    for p in (h.get("past") or []):
        nk = p.get("venue") in NANKAN
        if lo <= p["dist"] <= hi and p.get("t") and p.get("agari"):
            if nk:
                e.append((p["dist"] - 600) / (p["t"] - p["agari"]))
                # ★ 終いは「その場・その距離の後3Fの水準との差」にする。秒そのものではない。
                #   場が変われば上がりの水準が変わる（浦和800m 35.5 対 川崎900m 37.8＝2.3秒差）。
                b = B.get("%s|%d" % (p["venue"], p["dist"]))
                if b:
                    # 水準との差 ＋ 場間補正。川崎に揃えた値。小さいほど速い
                    l.append(p["agari"] - b["a3"] + VADJ.get(p["venue"], 0.0))
            else:
                ext += 1
        if p.get("c4"):
            c4.append((p["c4"] - 1) / max(1, p["n"] - 1))
    return (st.median(e) if e else None, st.median(l) if l else None,
            st.median(c4) if c4 else None, len(e), ext)


def race(v, ven):
    dist = v["dist"]
    rows = []
    for h in v["horses"]:
        e, l, c, n, ext = prof(h, dist)
        rows.append({"h": h, "e": e, "l": l, "c4": c, "n": n, "ext": ext})
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
                print("     ―  %2d %s 南関で測れる走なし%s" % (
                    r["h"]["ub"], w(r["h"]["name"], 14),
                    "（他場%d走あり／弱いという意味ではない）" % r["ext"] if r["ext"] else "")); continue
            print("    %2d番手 %2d %s 前半%.3f 終い%.3f  前3F%.1f 後3F%.1f  南関%d走%s" % (
                i + 1, r["h"]["ub"], w(r["h"]["name"], 14), r["e"], r["l"],
                600 / r["e"], 600 / r["l"], r["n"],
                " +他場%d" % r["ext"] if r["ext"] else ""))


if __name__ == "__main__":
    main()
