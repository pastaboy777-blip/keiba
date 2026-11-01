"""市場とのズレを見る ── 自分の並びと、オッズの並びの**順位差**だけを見る道具。

  python3 zure.py <card.json>            # 全鞍
  python3 zure.py <card.json> --R 7      # その鞍だけ

── なぜ「確率」ではなく「順位」で比べるか

この板の点は、**当てはめをしていない**（重みは手で置いたもの）。だから
softmax で確率に直しても、その**水準は信用できない**。
「自分は18%、市場は12%だから買い」という比べ方は、
温度を1つ手で決めただけで答えが変わる。**やらない。**

**順位どうしなら、水準の校正が要らない。**
自分が3番手に置いた馬を市場が9番人気にしている、というズレは、
点の目盛りが何であっても成り立つ。

  ★ 相対化の筋をもう一段 ── 順位は「この鞍の中」でしか意味を持たない。
    鞍をまたいで「ズレ+6」どうしを比べてはいけない（頭数が違う）。
    だから**頭数で割った値**も出してある。

── 使いかた（当日）

  前日はオッズが空なので「オッズ未入力」と出る。
  **発走30分前に出馬表を取り直して**から、もう一度これを回す。
  ルール3（馬体重の取り直し）と同じタイミング。

── 読み方

  ズレが大きい ＝ 自分だけが高く見ている馬。**当たれば配当がつく側**
  ズレが小さい ＝ 市場と同じことを言っている。**買っても妙味はない**

  ただし「自分だけが高く見ている」は「自分が間違っている」と同じ形をしている。
  ズレは**買う理由ではなく、見るべき馬を絞る**ためのもの。
"""
import sys, json, os, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kin5
from kukan import horse_fs, race_fs, sui


def band(d):
    return (d - 200, d + 200) if d >= 1200 else (0, 1000)


def score(v):
    """鞍のなかの点。board と同じ組み立て（FS%＋道中の動き＋位置）"""
    lo, hi = band(v["dist"])
    out = []
    for h in v["horses"]:
        f, g, r, bad = [], [], [], []
        for p in (h.get("past") or []):
            fs = horse_fs(p.get("t"), p.get("agari"), p["dist"])
            c, _ = sui(p["venue"], p["dist"], p["baba"])
            if lo <= p["dist"] <= hi and fs is not None and c:
                f.append(fs - c["fs"])
            if p.get("c1") and p.get("c4"):
                g.append(p["c1"] - p["c4"])
                r.append((p["c4"] - 1) / max(1, p["n"] - 1))
                rr = kin5.find_race(p, h["name"])
                if rr and c:
                    _, tt = race_fs(rr)
                    if tt is not None and tt - c["tt"] <= -0.3 and p["c1"] - p["c4"] <= -2:
                        bad.append(p)
        s = (st.median(f) if f else 0) + (st.median(g) * 0.6 if g else 0)
        if r:
            m = st.median(r)
            s += 1.0 if 0.30 <= m <= 0.55 else 0.3 if m < 0.15 else 0
        out.append({"h": h, "s": s, "bad": bool(bad)})
    return out


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    f = [x for x in a if x.endswith(".json")][0]
    R = int(a[a.index("--R") + 1]) if "--R" in a else None
    D = json.load(open(f))
    for k in sorted(D, key=int):
        v = D[k]
        if R and v["R"] != R:
            continue
        rows = score(v)
        n = len(rows)
        rows.sort(key=lambda x: -x["s"])
        for i, x in enumerate(rows):
            x["mine"] = i + 1
        # 市場の並び … 単勝オッズの低い順。nin（人気）があればそちら
        odds = [(x["h"].get("odds"), x) for x in rows]
        have = all(o is not None for o, _ in odds)
        print("\n%2dR ダ%4dm %2d頭  %s" % (v["R"], v["dist"], n, (v.get("cls") or "")[:20]))
        if not have:
            print("    オッズ未入力（前日の出馬表）。発走30分前に取り直してから回すこと")
            for x in rows[:5]:
                print("      自分%2d番手  %2d番 %s  %.1f%s" % (
                    x["mine"], x["h"]["ub"], kin5.w(x["h"]["name"], 15), x["s"],
                    "  ×" if x["bad"] else ""))
            continue
        for _, x in sorted(odds, key=lambda t: float(t[0])):
            pass
        srt = sorted(rows, key=lambda x: float(x["h"]["odds"]))
        for i, x in enumerate(srt):
            x["mkt"] = i + 1
        for x in sorted(rows, key=lambda x: x["mkt"] - x["mine"], reverse=True):
            d = x["mkt"] - x["mine"]
            print("      %2d番 %s 自分%2d / 市場%2d（%s倍）  ズレ%+3d  頭数あたり%+.2f%s" % (
                x["h"]["ub"], kin5.w(x["h"]["name"], 15), x["mine"], x["mkt"],
                x["h"]["odds"], d, d / n, "  ×" if x["bad"] else ""))


if __name__ == "__main__":
    main()
