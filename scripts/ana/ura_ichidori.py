"""浦和の直近3開催で、馬券になった馬（3着以内）がどこを走っていたかを並べる。

  python3 ura_ichidori.py                      # 画面に出す
  python3 ura_ichidori.py --out ../../notes/live/urawa_3kaisai_ichidori.md

ユーザーの指示（2026-11-22）「浦和3開催分　馬券になった馬の位置取りは把握しておいて！」
頼まれたのは「浦和3開催の3着内の位置取り」だけ。ほかの場・ふだんとの比較、回収率は出さない。

── 材料は harvest/ura<MMDD>_res.json だけ（楽天の結果頁から取ったもの）

  相対位置 … (順位−1)/(その角を通った頭数−1)。順位は通過順の塊で数える（同じ括弧は同順位）。
  最初の角 … その鞍で最初に記録された角（浦和800mは3角、ほかは1角）。
  gain     … 最初の角の相対 − 4角の相対（プラス＝前へ出た）。
  内外     … 4角で併走（括弧の中に2頭以上）したときの並び。括弧の先頭＝内、末尾＝外、間＝中
             （soto.py と同じ読み方）。単独の馬は内外不明（ルール14）。
  前3F/後3F… tenkai.py と同じ取り方。前3F＝ラップの最初が10秒未満（半端な100m）ならそれを
             除いた先頭3本の和、後3F＝最後の3本の和。**2つを混ぜない**（ルール37）。
  上がり順位… その鞍で上がりが取れた馬の中での順位（同タイムは同順位）。
             上がりが欠けた馬がいる鞍は「*」を付ける（順位が少しずれうる）。
  人気     … harvest の nk は人気ではない（ルール34）。結果データに人気欄が無いので「人気なし」。
"""
import os, sys, json, glob, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 開催 ＝ cal.json の回（base16 の15〜16桁目が日、13〜14桁目が回）
KAISAI = [
    ("第5回（8/7・8/10〜8/12）", ["0807", "0810", "0811", "0812"]),
    ("第6回（9/22〜9/25）", ["0922", "0923", "0924", "0925"]),
    ("第7回（10/19〜10/23）", ["1019", "1020", "1021", "1022", "1023"]),
]
BANDS = ["0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]
WAKU = ["1-2枠", "3-6枠", "7-8枠"]
UCHI = ["内", "中", "外", "単独（内外不明）"]


def band(x):
    return BANDS[min(int(x / 0.2 + 1e-9), 4)]


def wk(w):
    return WAKU[0] if w <= 2 else WAKU[2] if w >= 7 else WAKU[1]


def rel_map(seq):
    """通過順の塊のリスト → {馬番: 相対位置}, 頭数"""
    n = sum(len(g) for g in seq)
    out, rk = {}, 1
    for g in seq:
        for ub in g:
            out[ub] = (rk - 1) / (n - 1) if n > 1 else 0.0
        rk += len(g)
    return out, n


def side_map(seq):
    out = {}
    for g in seq:
        for i, ub in enumerate(g):
            out[ub] = UCHI[3] if len(g) == 1 else UCHI[0] if i == 0 else \
                UCHI[2] if i == len(g) - 1 else UCHI[1]
    return out


def f3a3(L):
    if not L:
        return None, None
    full = L[1:] if L[0] < 10 else L
    if len(full) < 4:
        return None, None
    return round(sum(full[:3]), 1), round(sum(L[-3:]), 1)


def load():
    horses, races, notes = [], [], []
    for kname, days in KAISAI:
        for d in days:
            f = os.path.join(HERE, "harvest", "ura%s_res.json" % d)
            if not os.path.exists(f):
                notes.append("%s/%s の結果ファイルが無い" % (d[:2], d[2:]))
                continue
            D = json.load(open(f))
            got = sorted(int(k) for k in D)
            for R in range(1, 13):
                if R not in got:
                    notes.append("%d/%d %dR は harvest に無い（楽天の結果頁に全着順が出ない＝取止めとみられる）"
                                 % (int(d[:2]), int(d[2:]), R))
            for k in sorted(D, key=int):
                r = D[k]
                cn = r.get("corner") or {}
                if not cn:
                    notes.append("%s %sR 通過順なし" % (d, k)); continue
                k1 = min(cn, key=int); k4 = "4" if "4" in cn else max(cn, key=int)
                p1, n1 = rel_map(cn[k1])
                p4, n4 = rel_map(cn[k4])
                sd4 = side_map(cn[k4])
                f3, a3 = f3a3(r.get("lap") or [])
                ag = [z["agari"] for z in r["rows"] if z.get("agari") is not None]
                agmiss = sum(1 for z in r["rows"] if z.get("agari") is None)
                rc = dict(kai=kname, d=d, R=r["R"], dist=r["dist"], baba=r["baba"], f3=f3, a3=a3,
                          k1=k1, n=len(r["rows"]), agmiss=agmiss)
                races.append(rc)
                for z in r["rows"]:
                    ub = z["ub"]
                    if ub not in p4 and ub not in p1:
                        continue
                    a = z.get("agari")
                    h = dict(rc, ub=ub, waku=z["waku"], name=z["name"], chaku=z["chaku"],
                             r1=p1.get(ub), r4=p4.get(ub), side=sd4.get(ub, UCHI[3]),
                             agari=a, agrk=(1 + sum(1 for x in ag if x < a)) if a is not None else None)
                    h["gain"] = (h["r1"] - h["r4"]) if h["r1"] is not None and h["r4"] is not None else None
                    h["top3"] = z["chaku"] is not None and z["chaku"] <= 3
                    horses.append(h)
    return horses, races, notes


def pct(a, b):
    return "%d/%d（%.1f%%）" % (a, b, 100 * a / b) if b else "0/0"


def table(H, key, cats, title):
    """cats の各段について、その段にいた頭数・3着内・率と、3着内の内訳"""
    out = ["| %s | 3着内/その段の頭数（率） |" % title, "|---|---|"]
    for c in cats:
        tot = [h for h in H if key(h) == c]
        t3 = [h for h in tot if h["top3"]]
        out.append("| %s | %s |" % (c, pct(len(t3), len(tot))))
    miss = [h for h in H if key(h) is None]
    if miss:
        out.append("| 記録なし | %s |" % pct(sum(h["top3"] for h in miss), len(miss)))
    return out


def fmt(x):
    return "-" if x is None else "%.2f" % x


def kado(k1):
    return "3角" if k1 == "3" else "%s角" % k1


def section(H, races, head, lvl="###"):
    rs = {(r["d"], r["R"]) for r in races}
    t3 = [h for h in H if h["top3"]]
    out = ["%s %s" % (lvl, head), "",
           "%d鞍・出走（通過順のある馬）%d頭・3着内%d頭" % (len(rs), len(H), len(t3)), ""]
    out += table(H, lambda h: band(h["r4"]) if h["r4"] is not None else None, BANDS, "4角の相対位置")
    out.append("")
    k1s = sorted({kado(r["k1"]) for r in races})
    out += table(H, lambda h: band(h["r1"]) if h["r1"] is not None else None, BANDS,
                 "最初の角（%s）の相対位置" % "・".join(k1s))
    out.append("")
    out += table(H, lambda h: wk(h["waku"]), WAKU, "枠")
    out.append("")
    out += table(H, lambda h: h["side"], UCHI, "4角の内外（併走時）")
    out.append("")
    out += table(H, lambda h: "8R以前" if h["R"] <= 8 else "9R以降（照明）", ["8R以前", "9R以降（照明）"], "時間帯")
    out.append("")
    g = [h["gain"] for h in t3 if h["gain"] is not None]
    if g:
        out.append("3着内の gain … 前へ出た（>0）%d頭／変わらず（=0）%d頭／下げた（<0）%d頭" %
                   (sum(x > 1e-9 for x in g), sum(abs(x) <= 1e-9 for x in g), sum(x < -1e-9 for x in g)))
        out.append("")
    back = sorted([h for h in t3 if h["r4"] is not None and h["r4"] >= 0.6],
                  key=lambda h: (h["d"], h["R"], h["chaku"]))
    out.append("**4角0.6以降から3着内に来た馬** … %d頭" % len(back))
    out.append("")
    if back:
        out.append("| 日 | R | 距離 | 馬場 | 着 | 馬番 | 馬名 | 最初の角 | 4角 | gain | 上がり(順位) | 前3F | 後3F |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for h in back:
            out.append(row(h))
        out.append("")
    return out


def row(h):
    ag = "-" if h["agari"] is None else "%.1f(%d%s)" % (h["agari"], h["agrk"], "*" if h["agmiss"] else "")
    return "| %d/%d | %d | %d | %s | %d | %d | %s | %s | %s | %s | %s | %s | %s |" % (
        int(h["d"][:2]), int(h["d"][2:]), h["R"], h["dist"], h["baba"], h["chaku"], h["ub"],
        h["name"], fmt(h["r1"]), fmt(h["r4"]), "-" if h["gain"] is None else "%+.2f" % h["gain"],
        ag, "-" if h["f3"] is None else "%.1f" % h["f3"], "-" if h["a3"] is None else "%.1f" % h["a3"])


def main():
    H, races, notes = load()
    t3 = [h for h in H if h["top3"]]
    days = [d for _, ds in KAISAI for d in ds]
    L = ["# 浦和 直近3開催 ── 3着内の馬の位置取り", "",
         "対象 … 浦和 **%s〜%s の%d日・%d鞍**。通過順のある出走 **%d頭**、うち3着内 **%d頭**"
         "（同着を含む）。" % ("%d/%d" % (int(days[0][:2]), int(days[0][2:])),
                          "%d/%d" % (int(days[-1][:2]), int(days[-1][2:])), len(days), len(races),
                          len(H), len(t3)),
         "", "開催 … " + "／".join("%s %d鞍" % (k, sum(1 for r in races if r["kai"] == k))
                                for k, _ in KAISAI), "",
         "集計スクリプト `scripts/ana/ura_ichidori.py`（数字はすべてこの出力）。"
         "材料は `scripts/ana/harvest/ura<MMDD>_res.json` だけ。", "",
         "## 読み方", "",
         "- 相対位置 ＝ (順位−1)/(その角を通った頭数−1)。0＝先頭、1＝最後方。同じ括弧の馬は同順位。",
         "- 段は 0-0.2 ＝ 0以上0.2未満 …、0.8-1.0 ＝ 0.8以上1.0以下。",
         "- 最初の角 ＝ その鞍で最初に記録された角（**800mは3角**、ほかの距離は1角）。",
         "- gain ＝ 最初の角の相対 − 4角の相対（プラス＝前へ出た）。",
         "- 率の分母は「その段にいた全馬」。3着内の頭数だけでなく必ず分母を付けた。",
         "- 内外 ＝ 4角で併走したときの並び（括弧の先頭＝内・末尾＝外・間＝中）。"
         "**単独の馬は内外が記録されない**ので「単独（内外不明）」（ルール14）。",
         "- 前3F・後3F ＝ `tenkai.py` と同じ取り方（前3Fは先頭が半端な100mならそれを除いた先頭3本、"
         "後3Fは最後の3本）。**前と後を混ぜない**（ルール37）。",
         "- **人気は出していない（人気なし）。** harvest の `nk` は人気ではなく（ルール34）、"
         "結果データに人気の欄が無い。",
         "- 上がり順位の「*」は、その鞍に上がりが取れていない馬がいる印（順位が少しずれうる）。",
         "- 9R以降＝照明が入る鞍（物差し6）。",
         "- この3開催に **1600mの鞍は無い**。1300mの鞍があるので足した。", ""]
    L += ["## 取れなかったデータ", ""]
    L += ["- " + n for n in notes] or ["- なし"]
    miss = [h for h in t3 if h["agari"] is None]
    L.append("- 3着内で上がりが取れていない馬 %d頭：" % len(miss) + "、".join(
        "%d/%d %dR %d着 %s" % (int(h["d"][:2]), int(h["d"][2:]), h["R"], h["chaku"], h["name"]) for h in miss))
    L.append("- 人気 … 全頭なし（上記）。")
    L.append("")

    dists = sorted({r["dist"] for r in races})
    L += ["## 距離ごと（3開催を通して）", ""]
    for dist in dists:
        Hd = [h for h in H if h["dist"] == dist]
        L += section(Hd, [r for r in races if r["dist"] == dist], "%dm" % dist)
    L += ["## 開催 × 距離 × 馬場", "",
          "各欄は **3着内／その段にいた頭数**。率は距離ごとの節（上）に出してある。", ""]
    order = [(k, dist, b) for k, _ in KAISAI for dist in dists for b in ["良", "稍重", "重", "不良"]]
    cells = []
    for kname, dist, baba in order:
        rr = [r for r in races if r["kai"] == kname and r["dist"] == dist and r["baba"] == baba]
        if rr:
            Hc = [h for h in H if h["kai"] == kname and h["dist"] == dist and h["baba"] == baba]
            cells.append((kname, dist, baba, rr, Hc))

    def cnt(Hc, key, c):
        tot = [h for h in Hc if key(h) == c]
        return "%d/%d" % (sum(h["top3"] for h in tot), len(tot))

    specs = [
        ("4角の相対位置", BANDS, lambda h: band(h["r4"]) if h["r4"] is not None else None),
        ("最初の角の相対位置（800mは3角・ほかは1角）", BANDS,
         lambda h: band(h["r1"]) if h["r1"] is not None else None),
        ("枠", WAKU, lambda h: wk(h["waku"])),
        ("4角の内外（併走時。単独は内外不明）", UCHI, lambda h: h["side"]),
        ("時間帯", ["8R以前", "9R以降（照明）"], lambda h: "8R以前" if h["R"] <= 8 else "9R以降（照明）"),
    ]
    for title, cats, key in specs:
        L += ["### " + title, "",
              "| 開催 | 距離 | 馬場 | 鞍 | " + " | ".join(cats) + " |",
              "|---|---|---|---|" + "---|" * len(cats)]
        for kname, dist, baba, rr, Hc in cells:
            L.append("| %s | %d | %s | %d | %s |" % (kname.split("（")[0], dist, baba, len(rr),
                     " | ".join(cnt(Hc, key, c) for c in cats)))
        L.append("")
    L += ["### 3着内の gain（前へ出た／変わらず／下げた）", "",
          "| 開催 | 距離 | 馬場 | 3着内 | 前へ出た | 変わらず | 下げた |", "|---|---|---|---|---|---|---|"]
    for kname, dist, baba, rr, Hc in cells:
        g = [h["gain"] for h in Hc if h["top3"] and h["gain"] is not None]
        L.append("| %s | %d | %s | %d | %d | %d | %d |" % (
            kname.split("（")[0], dist, baba, sum(h["top3"] for h in Hc),
            sum(x > 1e-9 for x in g), sum(abs(x) <= 1e-9 for x in g), sum(x < -1e-9 for x in g)))
    L.append("")
    L += ["## 3着内の全馬", "",
          "| 日 | R | 距離 | 馬場 | 着 | 馬番 | 枠 | 馬名 | 最初の角 | 4角 | gain | 4角内外 | 上がり(順位) | 前3F | 後3F | 人気 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for h in sorted(t3, key=lambda h: (h["d"], h["R"], h["chaku"])):
        ag = "-" if h["agari"] is None else "%.1f(%d%s)" % (h["agari"], h["agrk"], "*" if h["agmiss"] else "")
        L.append("| %d/%d | %d | %d | %s | %d | %d | %d | %s | %s | %s | %s | %s | %s | %s | %s | 人気なし |" % (
            int(h["d"][:2]), int(h["d"][2:]), h["R"], h["dist"], h["baba"], h["chaku"], h["ub"], h["waku"],
            h["name"], fmt(h["r1"]), fmt(h["r4"]), "-" if h["gain"] is None else "%+.2f" % h["gain"],
            h["side"].replace("（内外不明）", ""), ag,
            "-" if h["f3"] is None else "%.1f" % h["f3"], "-" if h["a3"] is None else "%.1f" % h["a3"]))
    L.append("")
    txt = "\n".join(L)
    if "--out" in sys.argv:
        p = sys.argv[sys.argv.index("--out") + 1]
        open(p, "w").write(txt)
        print("書いた → %s（%d行）" % (p, len(L)))
    else:
        print(txt)


if __name__ == "__main__":
    main()
