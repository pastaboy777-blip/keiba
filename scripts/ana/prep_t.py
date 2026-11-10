"""出馬表 → mk*.py が食べる t.json（隊列図用の1頭1行）。

  python3 prep_t.py <card.json> <out_t.json>

★ srank（終い順位）は 2026-11-10 から **昇順**。
  tenkai.prof の2つめは「その場・その距離の後3F水準との差＋場間補正」で、
  小さいほど速い。前の t.json は速度のまま降順で作られていたので作り直すこと。
"""
import sys, os, json, datetime as dt

HERE = "/home/user/keiba/scripts/ana"
sys.path.insert(0, HERE)
import tenkai as T

TODAY = dt.date(2026, 11, 10)
SOTO = os.path.join(HERE, "soto.json")


def rel(p, key):
    if not p.get(key) or not p.get("n"):
        return None
    return (p[key] - 1) / max(1, p["n"] - 1)


def main():
    card, out = sys.argv[1], sys.argv[2]
    D = json.load(open(card))
    SO = json.load(open(SOTO)) if os.path.exists(SOTO) else {}
    R = {}
    for k in sorted(D, key=int):
        v = D[k]
        dist = v["dist"]
        rows = []
        for h in v["horses"]:
            P = h.get("past") or []
            c4 = [rel(p, "c4") for p in P]; c4 = [x for x in c4 if x is not None]
            c1 = [rel(p, "c1") for p in P]; c1 = [x for x in c1 if x is not None]
            import statistics as st
            pos = st.median(c4) if c4 else None
            gain = (st.median(c1) - pos) if (c1 and pos is not None) else None
            e, l, _c, n, ext = T.prof(h, dist)
            s = SO.get(h["name"])
            ven = {}
            for p in P:
                ven[p["venue"]] = ven.get(p["venue"], 0) + 1
            gap = dd = chaku = n0 = None
            if P:
                p0 = P[0]
                y, m, d = (int(x) for x in p0["date"].split("."))
                gap = (TODAY - dt.date(2000 + y, m, d)).days
                dd = dist - p0["dist"]; chaku = p0["chaku"]; n0 = p0["n"]
            rows.append(dict(ub=h["ub"], waku=h.get("waku"), name=h["name"],
                             pos=pos, gain=gain,
                             soto=(s["out"] / s["grp"]) if s and s["grp"] >= 3 else None,
                             sn=(s["grp"] if s else 0),
                             l=l, e=e, ext=ext, runs=len(P), ven=ven,
                             gap=gap, dd=dd, chaku=chaku, n0=n0, srank=None))
        # ★ 終いは小さいほど速い。昇順で順位を振る
        for i, r in enumerate(sorted([x for x in rows if x["l"] is not None],
                                     key=lambda x: x["l"]), 1):
            r["srank"] = i
        R[k] = dict(R=v["R"], dist=dist, cls=v.get("cls") or "", start=v.get("start") or "",
                    n=len(v["horses"]), rows=rows)
    json.dump(R, open(out, "w"), ensure_ascii=False, indent=1)
    print("%d鞍 → %s" % (len(R), out))


main()
