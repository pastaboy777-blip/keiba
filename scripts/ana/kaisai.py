"""今開催（第11回大井）に出走した全馬を引く ── 今開催の走り＋その前の近5走。

  python3 kaisai.py <馬名の一部>            # 馬で引く
  python3 kaisai.py --day 1028 --R 7        # その鞍の全頭
  python3 kaisai.py --day 1028              # その日の全鞍（1行ずつ）
  python3 kaisai.py --stat                  # 収録状況

データ … scripts/ana/ooi11_kaisai.json（423頭）

── 入っているもの

  今開催の走り   日・R・距離・馬場・頭数・馬番・枠・着順・人気・1角・4角・
                 上がり3F・馬体重・増減・騎手・調教師
  その前の近5走  日付・場・馬場・距離・頭数・人気・着順・着差・
                 自前半・上がり3F・走破タイム・通過順・馬体重・そのときの枠

  ★ 自前半 ＝ 走破タイム − 上がり3F。楽天は前半を出さないが引き算で出る。
  ★ 近5走から「今開催ぶん」は抜いてある（10/26以降の大井は重複するため）。

── 分かっていること（2026-10-29 時点）

  3日で **のべ423頭＝実423頭**。**同じ馬が2回使われた例はゼロ。**
  10/26・27 が全鞍「不良」、10/28 が全鞍「重」。
  近5走を5走ぶん持つのは264頭。**55頭は過去走ゼロ**（2歳初出走・転入初戦など）。
  CLAUDE.md ルール6 ── 履歴が引けないことを弱さと読まない。

  距離の内訳 … 1200m 13鞍 / 1600m 11鞍 / 1400m 7鞍 / 1800m 2鞍 /
                1000m・2000m・2400m 各1鞍
"""
import sys, json, os, unicodedata as ud

HERE = os.path.dirname(os.path.abspath(__file__))
# ★ harvest/ は .gitignore で除外されるので、本体はこのディレクトリに置く
DATA = os.path.join(HERE, "ooi11_kaisai.json")
if not os.path.exists(DATA):
    DATA = os.path.join(HERE, "harvest", "ooi11_kaisai.json")


def w(s, n):
    l = sum(2 if ud.east_asian_width(c) in "FW" else 1 for c in s)
    return s + " " * max(0, n - l)


def line_now(r):
    return "今開催 %s %2dR ダ%4d %s %2d頭 %2d番%s枠 %s着 %s人気 1角%s 4角%s 上%s %s%s %s/%s" % (
        r["date"][5:], r["R"], r["dist"], r["baba"] or "?", r["n"], r["ub"],
        r.get("waku") or "?", r["chaku"] if r["chaku"] else "-",
        r["nk"] if r["nk"] else "-", r.get("c1") or "?", r.get("c4") or "?",
        ("%.1f" % r["agari"]) if r.get("agari") else "?",
        r.get("w") or "?", r.get("dw") or "", r.get("jk") or "?", r.get("tr") or "?")


def line_past(p):
    return "  近走 %s %s %s %4d %2d頭 %2d人 %2d着 %+.1f 前半%s+上%s=%s 通%s 体%s" % (
        p["date"], p["venue"], p["baba"], p["dist"], p["n"], p["nk"], p["chaku"],
        p["sa"], p.get("zen"), p.get("agari"), p.get("t"),
        "-".join(str(x) for x in p["tsuka"]), p.get("w"))


def show(e, past=True):
    print("\n■ %s" % e["name"])
    for r in e["kaisai"]:
        print("  " + line_now(r))
    if past:
        for p in e["past5"]:
            print(line_past(p))
        if not e["past5"]:
            print("  近走なし（過去走が引けない馬。弱いという意味ではない）")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    H = json.load(open(DATA))
    if "--stat" in a:
        from collections import Counter
        c = Counter(len(e["past5"]) for e in H.values())
        d = Counter(r["dist"] for e in H.values() for r in e["kaisai"])
        b = Counter(r["baba"] for e in H.values() for r in e["kaisai"])
        print("収録 %d頭 ／ のべ出走 %d" % (
            len(H), sum(len(e["kaisai"]) for e in H.values())))
        print("近5走の保持 … " + " / ".join("%d走%d頭" % (k, c[k]) for k in sorted(c, reverse=True)))
        print("距離 … " + " / ".join("%dm %d頭" % (k, d[k]) for k in sorted(d)))
        print("馬場 … " + " / ".join("%s %d頭" % (k, b[k]) for k in b if k))
        return
    if "--day" in a:
        day = a[a.index("--day") + 1]
        R = int(a[a.index("--R") + 1]) if "--R" in a else None
        rows = [(r, e) for e in H.values() for r in e["kaisai"]
                if r["date"][5:7] + r["date"][8:10] == day and (R is None or r["R"] == R)]
        rows.sort(key=lambda x: (x[0]["R"], x[0]["chaku"] or 99))
        if R is None:
            for r, e in rows:
                print("%2dR %2d番 %s %s着 %s人気 4角%s 上%s %s%s" % (
                    r["R"], r["ub"], w(e["name"], 15), r["chaku"] or "-", r["nk"] or "-",
                    r.get("c4") or "?", ("%.1f" % r["agari"]) if r.get("agari") else "?",
                    r.get("w") or "?", r.get("dw") or ""))
        else:
            for r, e in rows:
                show(e)
        return
    q = a[0]
    hit = [e for nm, e in H.items() if q in nm]
    if not hit:
        print("%s に当たる馬がいません（今開催の出走馬は423頭）" % q); return
    for e in sorted(hit, key=lambda e: e["name"]):
        show(e)


if __name__ == "__main__":
    main()
