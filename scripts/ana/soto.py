"""馬ごとの「外に出せるか」── 4角で併走したとき、外側にいた割合。

  python3 soto.py --build                 # soto.json を作る（harvest/ 全部から）
  python3 soto.py --build --before 1102   # 11/02 より前の鞍だけで作る（循環よけ）
  python3 soto.py <馬名の一部>             # 1頭を引く
  python3 soto.py --card <card.json>      # 出馬表の全頭を鞍ごとに出す
  python3 soto.py --stat                  # 全体の数字

── なぜ使えるか（南関1,326鞍・3,265組で測った）

  通過順の括弧は**内→外**の並び。だから併走した組のどちら側にいたかが分かる。

    組の中の位置      頭数      1着            3着内
    いちばん内      3,259頭   6.9%          23.5%
    中            726頭   6.2%          20.5%
    いちばん外      3,263頭  **11.2%**      31.0%
    単独（併走なし）  8,130頭   8.5%          25.3%

  **いちばん外 11.2% ＞ 単独 8.5% ＞ いちばん内 6.9%。**
  併走するなら外。内で挟まれるのは単独より悪い。

  直接対決でも 外が上 55.5% 対 内が上 44.4%（3,265組）。

  場ごとに差がある ── 船橋 64.9% ／ 浦和 59.0% ／ 川崎 56.4% ／ 大井 54.5%。
  **船橋がいちばん極端。**

── ★ CLAUDE.md の「照明が入る鞍はラチ沿い加点」とは別物

  あちらは浦和9R以降、**内をロスなく追走する**話。
  こちらは**直線で外に出せるか**。向きが逆なので、混ぜないこと。

── ★ 基準は50%ではない

  2頭併走なら外にいられるのは1/2、3頭なら1/3。だから**構造的な平均が45%**。
  985頭（併走3回以上）の中央値43%・平均45%。
  **50%を境にすると半分以上を「外に出せる」と誤って拾う。**

    下から10% … 0%  ／ 25% … 25%  ／ 50% … 43%  ／ 75% … 67%  ／ 90% … 78%

  目安 … 60%以上を「外に出せる」（341頭）、25%以下を「内に入りがち」（265頭）。

── ★ 限界（必ず読むこと）

  1. harvest/ に取ってある鞍しか数えられない。4,007頭のうち
     **併走3回以上あるのは985頭だけ**。残りは率を出しても当てにならない。
  2. **その馬を評価したいレース自体がDBに入っていると循環する。**
     11/2の船橋を harvest したあとにキタサンライザーを引くと「外率100%（2回）」
     と出るが、その2回のうち1回は**勝った当のレース**。
     予想に使うときは、対象日より前の harvest だけで作り直すこと。
  3. 単独（併走なし）は外率に入らない。単独の多い馬は n が伸びない。
"""
import sys, json, os, re, glob, collections

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "soto.json")
VEN = {"ooi": "大井", "fun": "船橋", "ura": "浦和", "kaw": "川崎"}


def build(before=None):
    """before に MMDD を渡すと、その日より前の harvest だけで作る。
    ★ 予想に使うときは必ず渡すこと。当日のレースが入っていると、
      勝った当のレースを根拠にしてしまう（docstring の限界2）。"""
    H = collections.defaultdict(lambda: {"grp": 0, "out": 0, "in": 0, "mid": 0,
                                         "solo": 0, "ven": collections.Counter()})
    races = 0
    for f in sorted(glob.glob(os.path.join(HERE, "harvest", "*_res.json"))):
        base = os.path.basename(f)
        ven = VEN.get(base[:3])
        if not ven:
            continue
        m = re.search(r"(\d{4})", base)
        if before and m and m.group(1) >= before:
            continue
        try:
            D = json.load(open(f))
        except Exception:
            continue
        for k in D:
            r = D[k]
            seq = (r.get("corner") or {}).get("4")
            if not seq:
                continue
            races += 1
            nm = {z["ub"]: z["name"] for z in r["rows"] if z.get("name")}
            for g in seq:
                for i, ub in enumerate(g):
                    if ub not in nm:
                        continue
                    e = H[nm[ub]]
                    if len(g) == 1:
                        e["solo"] += 1
                        continue
                    e["grp"] += 1
                    e["ven"][ven] += 1
                    if i == len(g) - 1:
                        e["out"] += 1
                    elif i == 0:
                        e["in"] += 1
                    else:
                        e["mid"] += 1
    out = {n: {"grp": e["grp"], "out": e["out"], "in": e["in"], "mid": e["mid"],
               "solo": e["solo"], "ven": dict(e["ven"])} for n, e in H.items()}
    json.dump(out, open(DB, "w"), ensure_ascii=False, indent=0, sort_keys=True)
    g = sum(e["grp"] for e in out.values())
    print("%d鞍 / %d頭 / 併走のべ%d回 → %s" % (races, len(out), g, DB))


def rate(e):
    return (e["out"] / e["grp"]) if e["grp"] else None


def line(nm, e):
    r = rate(e)
    mark = ""
    if e["grp"] >= 3 and r is not None:
        mark = " ★外に出せる" if r >= 0.60 else " ※内に入りがち" if r <= 0.25 else ""
    return "%-16s 併走%2d回 外%2d 中%2d 内%2d ／ 単独%2d回  外率 %s%s" % (
        nm[:16], e["grp"], e["out"], e["mid"], e["in"], e["solo"],
        ("%.0f%%" % (100 * r)) if r is not None else "―", mark)


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    if "--build" in a:
        b = a[a.index("--before") + 1] if "--before" in a else None
        global DB
        if b:
            DB = os.path.join(HERE, "soto_%s.json" % b)
        build(b); return
    if "--db" in a:
        DB = a[a.index("--db") + 1]
    if not os.path.exists(DB):
        print("soto.json がない。--build を先に"); return
    H = json.load(open(DB))
    if "--stat" in a:
        g = sum(e["grp"] for e in H.values())
        o = sum(e["out"] for e in H.values())
        n3 = sum(1 for e in H.values() if e["grp"] >= 3)
        print("%d頭 ／ 併走のべ%d回 ／ 外側 %d回 (%.1f%%)" % (len(H), g, o, 100 * o / g))
        print("併走3回以上ある馬 … %d頭（率を見てよいのはここまで）" % n3)
        return
    if "--card" in a:
        import unicodedata as ud
        D = json.load(open(a[a.index("--card") + 1]))
        for k in sorted(D, key=int):
            v = D[k]
            print("\n%2dR ダ%dm %d頭" % (v["R"], v["dist"], len(v["horses"])))
            rs = []
            for h in v["horses"]:
                e = H.get(h["name"])
                rs.append((rate(e) if e and e["grp"] >= 3 else -1, h, e))
            for r, h, e in sorted(rs, key=lambda x: -x[0]):
                if not e or not e["grp"]:
                    print("   %2d %-16s 併走の記録なし" % (h["ub"], h["name"][:16])); continue
                print("   %2d %s" % (h["ub"], line(h["name"], e)))
        return
    # ★ --db / --before の「値」を馬名と取り違えないこと（orite.py で踏んだのと同じ穴）
    skip = {a.index(f) + 1 for f in ("--db", "--before", "--card") if f in a}
    pos = [x for i, x in enumerate(a) if not x.startswith("--") and i not in skip]
    if not pos:
        print(__doc__); return
    q = pos[0]
    hit = [(n, e) for n, e in H.items() if q in n]
    if not hit:
        print("%s に当たる馬がいません" % q); return
    for n, e in sorted(hit):
        print(line(n, e))
        if e["ven"]:
            print("   場 … " + " / ".join("%s%d回" % (k, v) for k, v in sorted(e["ven"].items())))


if __name__ == "__main__":
    main()
