"""大井の傾向・パターンを harvest の結果から数える（スタートの図・直線の図の2枚ぶん）。

  python3 ooi_keikou.py [<harvestのフォルダ>] [--json out.json] [--md out.md]

既定のフォルダは harvest_ooi3y/（ooi3y.py が集めた大井3年ぶん）。

★ 2026-11-26、ユーザーの依頼 ──「過去3年分　大井競馬の展開隊列図　データ取って！」
  「スタートと直線の2枚ね。ラップと位置と馬券になった馬のポジション」
  「傾向とかパターンとか」「馬場状態による狙いとか」「騎手の傾向とか」。

★ 数えるのは**着順と位置と時計だけ**。回収率は出さない（ルール★★★ ── 測るかはユーザーが決める）。
  騎手の「人気以上に来るか」は、人気ごとの3着内率（同じデータで出した平均）との差で見る。

── 物差し

  相対位置 rel = (通過順位 − 1) / (頭数 − 1)。0 が先頭・1 が最後方。
  スタートの図 … **最初に記録された角**（1000/1200m は3角、1400m は2角、1600m以上は1角、
                 2400m は1周目の3角）。c1 があればそれ、無ければ corner_raw のいちばん若い角。
  直線の図     … 4角（c4）。
  ペース       … 前3F − 後3F（秒）。−1.0 未満=前傾が緩い(S)／±1.0=M／それ以外… ではなく
                 大井はほぼ全鞍が前3F＜後3F なので、**同じ距離・馬場の中央値との差**で分ける
                 （速い＝中央値より0.5秒以上速い／遅い＝0.5秒以上遅い）。
  内外         … 4角の括弧（併走）の中で、いちばん内／いちばん外／単独。括弧は内→外の並び（soto.py）。
"""
import os, sys, re, json, glob, collections, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
BUCKETS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
BL = ["0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]
BABA = ["良", "稍重", "重", "不良"]


def groups(s):
    """'(3,5),7=4-1,6' → [[3,5],[7],[4],[1],[6]]"""
    out = []
    for m in re.finditer(r"\(([^)]*)\)|(\d+)", s or ""):
        if m.group(1) is not None:
            g = [int(x) for x in re.findall(r"\d+", m.group(1))]
            if g:
                out.append(g)
        else:
            out.append([int(m.group(2))])
    return out


def pos_of(gs, ub):
    p = 1
    for g in gs:
        if ub in g:
            return p
        p += len(g)
    return None


def bucket(x):
    for i, (a, b) in enumerate(BUCKETS):
        if a <= x < b:
            return i
    return len(BUCKETS) - 1


def dist_key(d):
    return "%dm" % d


def fix_nin(rows):
    """harvest の nk を人気（nin）に直す。2026-11-27 に確かめた。
    nk は行のいちばん最後の数字で、**最後の行（最下位の馬）以外は単勝人気そのもの**。
    最後の行だけは、うしろに続く「払戻金 … ◯番人気」まで切らずに拾っていて、
    払戻の最後の「◯番人気」が入っている。
    → 最後の行以外が 1〜n のうち1つだけ欠けた並びなら、欠けた番号が最後の行の人気。
      それ以外の形（取消・同着などで並びが崩れた鞍）は、その鞍ごと None にする。
    大井3年分 3,414鞍のうち 3,289鞍（96%）で人気が戻る。"""
    n = len(rows)
    ks = [r.get("nk") for r in rows]
    full = set(range(1, n + 1))
    if sorted(k for k in ks if k) == sorted(full) and None not in ks:
        nin = ks
    else:
        head = ks[:-1]
        miss = full - set(head)
        if None not in head and len(set(head)) == n - 1 and len(miss) == 1:
            nin = head + [miss.pop()]
        else:
            nin = [None] * n
    for r, k in zip(rows, nin):
        r["nin"] = k


def load(folder):
    races = []
    for f in sorted(glob.glob(os.path.join(folder, "ooi*_res.json"))):
        m = re.search(r"ooi(\d{8}|\d{4})", os.path.basename(f))
        day = m.group(1) if m else ""
        try:
            D = json.load(open(f))
        except Exception:
            continue
        for k, v in D.items():
            fix_nin(v.get("rows", []))
            rows = [r for r in v.get("rows", []) if r.get("chaku")]
            if len(rows) < 5 or not v.get("dist") or not v.get("baba"):
                continue
            cr = v.get("corner_raw") or {}
            first_key = min(cr, key=lambda x: int(x)) if cr else None
            g1 = groups(cr.get(first_key)) if first_key else []
            g4 = groups(cr.get("4")) if cr.get("4") else []
            N = len(rows)
            # 上がり順位（同タイムは同順位）
            ags = sorted(r["agari"] for r in rows if r.get("agari"))
            for r in rows:
                c1 = r.get("c1") or (pos_of(g1, r["ub"]) if g1 else None)
                c4 = r.get("c4") or (pos_of(g4, r["ub"]) if g4 else None)
                r["_r1"] = (c1 - 1) / (N - 1) if c1 else None
                r["_r4"] = (c4 - 1) / (N - 1) if c4 else None
                r["_agr"] = (ags.index(r["agari"]) + 1) if r.get("agari") else None
                # 4角の内外
                side = None
                for g in g4:
                    if r["ub"] in g:
                        side = "単独" if len(g) == 1 else ("内" if g[0] == r["ub"] else
                                                          ("外" if g[-1] == r["ub"] else "中"))
                r["_side"] = side
            L = v.get("lap") or []
            full = L[1:] if L and L[0] < 10 else L
            f3 = round(sum(full[:3]), 1) if len(full) >= 4 else None
            a3 = round(sum(L[-3:]), 1) if len(L) >= 4 else None
            races.append({"day": day, "R": k, "dist": v["dist"], "baba": v["baba"], "N": N,
                          "lap": L, "f3": f3, "a3": a3, "t": round(sum(L), 1) if L else None,
                          "rows": rows})
    return races


def rate(a, b):
    return round(100.0 * a / b, 1) if b else None


def main():
    a = sys.argv[1:]
    folder = next((x for x in a if not x.startswith("--") and os.path.isdir(x)),
                  os.path.join(HERE, "harvest_ooi3y"))
    races = load(folder)
    R = {"folder": folder, "races": len(races),
         "days": len({r["day"] for r in races}),
         "span": [min(r["day"] for r in races), max(r["day"] for r in races)] if races else None}

    # ── 人気ごとの3着内率（騎手の期待値に使う）
    pop = collections.Counter(); pop3 = collections.Counter()
    for rc in races:
        for r in rc["rows"]:
            if r.get("nin"):
                pop[r["nin"]] += 1; pop3[r["nin"]] += r["chaku"] <= 3
    exp3 = {k: pop3[k] / pop[k] for k in pop}
    R["ninki_3nai"] = {k: [pop[k], rate(pop3[k], pop[k])] for k in sorted(pop)}

    # ── 距離×馬場のセル
    def cells(rc):
        return [(dist_key(rc["dist"]), "全"), (dist_key(rc["dist"]), rc["baba"]),
                ("全距離", rc["baba"]), ("全距離", "全")]

    lapc = collections.defaultdict(lambda: {"t": [], "f3": [], "a3": [], "lap": []})
    for rc in races:
        for c in cells(rc):
            if rc["f3"] is not None:
                lapc[c]["t"].append(rc["t"]); lapc[c]["f3"].append(rc["f3"]); lapc[c]["a3"].append(rc["a3"])
            if rc["dist"] and c[0] != "全距離":
                lapc[c]["lap"].append(rc["lap"])
    R["lap"] = {}
    for c, v in lapc.items():
        if len(v["t"]) < 5:
            continue
        laps = [l for l in v["lap"] if l]
        ln = collections.Counter(len(l) for l in laps).most_common(1)
        mean_lap = None
        if ln:
            same = [l for l in laps if len(l) == ln[0][0]]
            mean_lap = [round(st.median(x), 1) for x in zip(*same)]
        R["lap"]["%s|%s" % c] = {"n": len(v["t"]), "t": round(st.median(v["t"]), 1),
                                "f3": round(st.median(v["f3"]), 1), "a3": round(st.median(v["a3"]), 1),
                                "lap": mean_lap}

    # ペース区分（同じ距離・馬場の前3F中央値との差）
    for rc in races:
        ref = R["lap"].get("%s|%s" % (dist_key(rc["dist"]), rc["baba"])) or \
              R["lap"].get("%s|全" % dist_key(rc["dist"]))
        rc["pace"] = None
        if ref and rc["f3"] is not None:
            d = rc["f3"] - ref["f3"]
            rc["pace"] = "速い" if d <= -0.5 else ("遅い" if d >= 0.5 else "ふつう")

    # ── 位置 → 3着内率（スタートの図 r1 ／ 直線の図 r4）
    def pos_table(key, extra=None):
        T = collections.defaultdict(lambda: [[0, 0] for _ in BUCKETS])
        for rc in races:
            cs = cells(rc)
            if extra:
                cs = cs + [(c[0], "ペース" + rc["pace"]) for c in cs if c[1] == "全" and rc["pace"]]
            for r in rc["rows"]:
                x = r.get(key)
                if x is None:
                    continue
                b = bucket(x)
                for c in cs:
                    T[c][b][0] += 1; T[c][b][1] += r["chaku"] <= 3
        return {"%s|%s" % c: [[n, rate(w, n)] for n, w in v] for c, v in T.items()
                if sum(n for n, _ in v) >= 50}
    R["start_pos"] = pos_table("_r1")
    R["choku_pos"] = pos_table("_r4", extra=True)

    # ── 馬券になった馬（3着内）の位置の分布（どこから来たか）
    def from_table(key):
        T = collections.defaultdict(lambda: [0] * len(BUCKETS))
        for rc in races:
            for r in rc["rows"]:
                if r["chaku"] <= 3 and r.get(key) is not None:
                    for c in cells(rc):
                        T[c][bucket(r[key])] += 1
        return {"%s|%s" % c: [sum(v)] + [rate(x, sum(v)) for x in v] for c, v in T.items() if sum(v) >= 30}
    R["start_from"] = from_table("_r1")
    R["choku_from"] = from_table("_r4")

    # ── 位置×上がり、押し上げ／下げ
    combo = collections.defaultdict(lambda: collections.Counter())
    for rc in races:
        for r in rc["rows"]:
            if r.get("_r4") is None or r.get("_agr") is None:
                continue
            k = ("4角0.2以内" if r["_r4"] <= 0.2 else "4角0.2超") + "×" + \
                ("上がり3位以内" if r["_agr"] <= 3 else "上がり4位以下")
            for c in cells(rc):
                combo["%s|%s" % c][k + "|n"] += 1
                combo["%s|%s" % c][k + "|w"] += r["chaku"] <= 3
            if r.get("_r1") is not None:
                g = r["_r1"] - r["_r4"]
                gk = "押し上げ(0.2以上)" if g >= 0.2 else ("下げた(0.2以上)" if g <= -0.2 else "ほぼ同じ")
                for c in cells(rc):
                    combo["%s|%s" % c]["gain:" + gk + "|n"] += 1
                    combo["%s|%s" % c]["gain:" + gk + "|w"] += r["chaku"] <= 3
    R["combo"] = {}
    for c, v in combo.items():
        out = {}
        for k in {x.rsplit("|", 1)[0] for x in v}:
            out[k] = [v[k + "|n"], rate(v[k + "|w"], v[k + "|n"])]
        R["combo"][c] = out

    # ── 枠・4角の内外
    waku = collections.defaultdict(lambda: [[0, 0] for _ in range(9)])
    side = collections.defaultdict(lambda: collections.Counter())
    for rc in races:
        for r in rc["rows"]:
            for c in cells(rc):
                if 1 <= r.get("waku", 0) <= 8:
                    waku["%s|%s" % c][r["waku"]][0] += 1
                    waku["%s|%s" % c][r["waku"]][1] += r["chaku"] <= 3
                if r.get("_side"):
                    side["%s|%s" % c][r["_side"] + "|n"] += 1
                    side["%s|%s" % c][r["_side"] + "|w"] += r["chaku"] <= 3
    R["waku"] = {c: [[n, rate(w, n)] for n, w in v[1:]] for c, v in waku.items()
                 if sum(n for n, _ in v) >= 100}
    R["side"] = {c: {s: [v[s + "|n"], rate(v[s + "|w"], v[s + "|n"])] for s in ("内", "中", "外", "単独")}
                 for c, v in side.items()}

    # ── 騎手
    J = collections.defaultdict(lambda: collections.Counter())
    for rc in races:
        wet = "良" if rc["baba"] == "良" else ("稍重" if rc["baba"] == "稍重" else "重・不良")
        for r in rc["rows"]:
            j = r.get("jk")
            if not j:
                continue
            c = J[j]; t3 = r["chaku"] <= 3
            c["n"] += 1; c["w3"] += t3; c["w1"] += r["chaku"] == 1
            if r.get("nin") in exp3:
                c["e3"] += exp3[r["nin"]]; c["ne"] += 1; c["w3e"] += t3
            if r.get("_r1") is not None:
                c["n1"] += 1; c["mae1"] += r["_r1"] <= 0.2
            if r.get("_r1") is not None and r.get("_r4") is not None:
                c["ng"] += 1; c["g"] += r["_r1"] - r["_r4"]
            if r.get("_r4") is not None:
                c["n4"] += 1; c["mae4"] += r["_r4"] <= 0.2
            if r.get("_side") in ("内", "外", "中"):
                c["np"] += 1; c["soto"] += r["_side"] == "外"
            c["n_" + wet] += 1; c["w_" + wet] += t3
            c["n_" + dist_key(rc["dist"])] += 1; c["w_" + dist_key(rc["dist"])] += t3
    R["jockey"] = {}
    for j, c in J.items():
        if c["n"] < 100:
            continue
        d = {"n": c["n"], "1着": rate(c["w1"], c["n"]), "3着内": rate(c["w3"], c["n"]),
             "人気比": round(100.0 * (c["w3e"] - c["e3"]) / c["ne"], 1) if c["ne"] else None,
             "1角先行": rate(c["mae1"], c["n1"]), "4角0.2以内": rate(c["mae4"], c["n4"]),
             "押し上げ平均": round(c["g"] / c["ng"], 3) if c["ng"] else None,
             "併走で外": rate(c["soto"], c["np"]), "併走n": c["np"]}
        for wet in ("良", "稍重", "重・不良"):
            d[wet] = [c["n_" + wet], rate(c["w_" + wet], c["n_" + wet])]
        d["距離"] = {k[2:]: [c[k], rate(c["w_" + k[2:]], c[k])] for k in c
                    if k.startswith("n_") and k.endswith("m") and c[k] >= 30}
        R["jockey"][j] = d

    # ── 年ごと（傾向が年をまたいで続いているか）
    yr = collections.defaultdict(lambda: [[0, 0] for _ in BUCKETS])
    for rc in races:
        y = rc["day"][:4] if len(rc["day"]) == 8 else "?"
        for r in rc["rows"]:
            if r.get("_r4") is not None:
                b = bucket(r["_r4"])
                for c in (("%s|%s" % (y, dist_key(rc["dist"]))), ("%s|全" % y)):
                    yr[c][b][0] += 1; yr[c][b][1] += r["chaku"] <= 3
    R["year_choku"] = {c: [[n, rate(w, n)] for n, w in v] for c, v in yr.items()
                       if sum(n for n, _ in v) >= 50}

    # ── 人気の帯ごと（2026-11-27 足した。人気は fix_nin で戻したもの）
    #   人気帯 × 直線の位置 / スタートの位置 / 押し上げ / 併走の内外 / 枠 → 3着内率
    #   「穴（6人気以下）はどこから来るか」を見るため。
    def nb(k):
        return None if not k else ("1番人気" if k == 1 else "2-3番人気" if k <= 3 else
                                   "4-5番人気" if k <= 5 else "6-9番人気" if k <= 9 else "10番人気以下")
    def gcls(r):
        if r.get("_r1") is None or r.get("_r4") is None:
            return None
        g = r["_r1"] - r["_r4"]
        return "押し上げ" if g >= 0.2 else "下げた" if g <= -0.2 else "ほぼ同じ"
    nk_ = collections.defaultdict(lambda: [0, 0])
    for rc in races:
        for r in rc["rows"]:
            b = nb(r.get("nin"))
            if not b:
                continue
            t3 = r["chaku"] <= 3
            for cell in (dist_key(rc["dist"]) + "|" + rc["baba"], dist_key(rc["dist"]) + "|全",
                         "全距離|" + rc["baba"], "全距離|全"):
                keys = ["全"]
                if r.get("_r4") is not None:
                    keys.append("直線" + BL[bucket(r["_r4"])])
                if r.get("_r1") is not None:
                    keys.append("スタート" + BL[bucket(r["_r1"])])
                if gcls(r):
                    keys.append("gain" + gcls(r))
                if r.get("_side"):
                    keys.append("併走" + r["_side"])
                keys.append("%d枠" % r["waku"])
                for kk in keys:
                    c = nk_[(cell, b, kk)]; c[0] += 1; c[1] += t3
    # ── 2026-11-27、枠 × 4角の前半/後半（馬場ごと）。外枠が効くのは前にいるときだけか。
    wm = collections.defaultdict(lambda: [0, 0])
    for rc in races:
        for r in rc["rows"]:
            if r.get("_r4") is None:
                continue
            g = "7-8枠" if r["waku"] >= 7 else ("1-2枠" if r["waku"] <= 2 else "3-6枠")
            h = "前半" if r["_r4"] < 0.5 else "後半"
            for bb in (rc["baba"], "全"):
                c = wm[(bb, g, h)]; c[0] += 1; c[1] += r["chaku"] <= 3
    R["waku_maeushiro"] = {"%s|%s|%s" % k: [n, rate(w, n)] for k, (n, w) in wm.items()}
    R["ninki_obi"] = {}
    for (cell, b, kk), (n, w) in nk_.items():
        R["ninki_obi"].setdefault(cell, {}).setdefault(b, {})[kk] = [n, rate(w, n)]

    # ── 2026-11-27、図の札（tenkai_zu.py --jk-ninhi）用に騎手の人気比だけ書き出す。
    #   300鞍以上の騎手だけ。値は「乗った馬の人気から見込む3着内率」との差（ポイント）。
    if "--jkjson" in a:
        out = {j: [v["n"], v["人気比"]] for j, v in R["jockey"].items()
               if v["n"] >= 300 and v["人気比"] is not None}
        json.dump(out, open(a[a.index("--jkjson") + 1], "w"), ensure_ascii=False, indent=0)

    if "--json" in a:
        json.dump(R, open(a[a.index("--json") + 1], "w"), ensure_ascii=False, indent=1)
    print("大井 %d日・%d鞍（%s … %s）" % (R["days"], R["races"], *(R["span"] or ["-", "-"])))
    for c in ("全距離|全", "1200m|全", "1400m|全", "1600m|全"):
        if c in R["choku_pos"]:
            print("直線(4角) %-10s" % c, R["choku_pos"][c])
        if c in R["start_pos"]:
            print("スタート  %-10s" % c, R["start_pos"][c])


if __name__ == "__main__":
    main()
