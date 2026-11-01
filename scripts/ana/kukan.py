"""区間で測る ── Finishing Speed %（香港JC）と Turn Time（Brohamer）。

  python3 kukan.py --baseline                      # 水準表をつくる（手元のラップ全部）
  python3 kukan.py --race <res.json> [R]           # その日の各鞍の FS% と TT
  python3 kukan.py --card <card.json> --R 7        # その鞍の全頭の FS%
  python3 kukan.py --card <card.json> <馬名>       # 1頭の近5走の FS%

── ① Finishing Speed %（香港ジョッキークラブ方式）

  **後半600mの速度 ÷ レース全体の平均速度 × 100**

  100%を超えれば終いのほうが速い。比なので**距離をまたいで比べられる**のが肝。
  秒やハロンタイムは距離が変わると比較できないが、これはできる。

  手元の船橋60鞍 … **57鞍が100%未満**。つまりほぼ全部、終いは平均より遅い。
  距離ごとの平均は 1000m 97.7 / 1200m 96.5 / **1500m 91.7** / 1600m 97.3。
  **船橋の1500mだけ極端に落ちる。**コースの性質がそのまま出る。

  ★ レースにも馬にも使える。
    レースのFS% … 公表ハロンタイムから。そのレースの形
    馬のFS%     … その馬の走破タイムと上がり3Fから。その馬がどう走ったか
    差（馬−レース）がプラスなら、**レースより終いを保った**

── ② Turn Time（Brohamer、アメリカのダート分析）

  **2ハロン目〜4ハロン目の3ハロン。**前半3Fでも上がり3Fでもない、勝負どころの手前。

  船橋 … 1200m で 35.0〜38.9（差3.9秒）、1600m で 36.9〜41.5（**差4.6秒**）。
  上がり3Fの差（2〜3秒）より大きい。**いちばん動く区間**。

  ★ こちらは**レースにしか使えない**。
    公表されるのはレースのハロンタイムだけで、個々の馬の2〜4F目は取れない。
    TTは「どういうレースだったか」を言う道具で、馬を評価する道具ではない。

── ★ 水準は場ごとに分ける

  同じ1500mでも船橋と大井は別物。水準表は **(場, 距離, 馬場)** で引く。
  薄いときは (場, 距離) に落とす。それも無ければ `水準なし`。
"""
import sys, json, os, glob, re, statistics as st, unicodedata as ud

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "kukan_base.json")
VEN = {"ooi": "大井", "fun": "船橋", "ura": "浦和", "kaw": "川崎"}


def w(s, n):
    l = sum(2 if ud.east_asian_width(c) in "FW" else 1 for c in s)
    while l > n:
        s = s[:-1]; l = sum(2 if ud.east_asian_width(c) in "FW" else 1 for c in s)
    return s + " " * max(0, n - l)


def laps(v):
    """★ 端数の扱いが FS% と TT で違う。

    1500m・1650m は先頭に端数ハロンが入る（船橋1500m=6.9秒/100m、大井1650m=3.9秒/50m）。

      FS%  … 端数も入れた**全ラップ合計 ÷ 実距離**。馬の走破タイムと同じ土俵にする
      TT   … 端数を落として**ハロンの目盛りを揃える**（2F目〜4F目を正しく取る）

    端数を落としたまま距離を 1500 のまま割ると、時間が足りず平均速度が過大になり、
    FS% が不当に低く出る（1500m が 91.7% に見えたのはこれが原因だった）。
    """
    L = v.get("lap") or []
    full = L[1:] if L and L[0] < 10 else L
    return L, full


def race_fs(v):
    L, full = laps(v); d = v["dist"]
    if len(full) < 4 or not d or not L:
        return None, None
    fs = 100 * (600 / sum(L[-3:])) / (d / sum(L))
    return fs, sum(full[1:4])


def horse_fs(t, agari, dist):
    """その馬の走破タイムと上がり3Fから。t も agari も無いと出ない"""
    if not (t and agari and dist):
        return None
    return 100 * (600 / agari) / (dist / t)


def build():
    cell = {}
    n = 0
    for f in glob.glob(os.path.join(HERE, "harvest", "*_res.json")):
        b = os.path.basename(f)[:3]
        ven = VEN.get(b)
        if not ven:
            continue
        try:
            D = json.load(open(f))
        except Exception:
            continue
        for k in D:
            v = D[k]
            fs, tt = race_fs(v)
            if fs is None:
                continue
            n += 1
            for key in ("%s|%d|%s" % (ven, v["dist"], v["baba"]), "%s|%d" % (ven, v["dist"])):
                cell.setdefault(key, {"fs": [], "tt": []})
                cell[key]["fs"].append(fs); cell[key]["tt"].append(tt)
    out = {"cell": {}, "n_races": n}
    for k, c in cell.items():
        if len(c["fs"]) >= 4:
            out["cell"][k] = {"fs": round(st.median(c["fs"]), 2),
                              "tt": round(st.median(c["tt"]), 2), "n": len(c["fs"])}
    json.dump(out, open(BASE, "w"), ensure_ascii=False, indent=0, sort_keys=True)
    print("水準表 … %dセル / 元データ %d鞍" % (len(out["cell"]), n))
    for k in sorted(out["cell"], key=lambda k: -out["cell"][k]["n"]):
        c = out["cell"][k]
        print("  %-16s %3d鞍  FS%% %.1f  TT %.1f" % (k, c["n"], c["fs"], c["tt"]))


def sui(ven, dist, baba=None):
    if not os.path.exists(BASE):
        return None, "水準表がない（--baseline を先に）"
    B = json.load(open(BASE))["cell"]
    if baba:
        c = B.get("%s|%d|%s" % (ven, dist, baba))
        if c:
            return c, "%s %dm %s（%d鞍）" % (ven, dist, baba, c["n"])
    c = B.get("%s|%d" % (ven, dist))
    return (c, "%s %dm 馬場まとめ（%d鞍）" % (ven, dist, c["n"])) if c else (None, "水準なし")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    if "--baseline" in a:
        build(); return
    if "--race" in a:
        f = a[a.index("--race") + 1]
        ven = VEN.get(os.path.basename(f)[:3], "?")
        only = [int(x) for x in a if x.isdigit()]
        D = json.load(open(f))
        print("%s ── Finishing Speed %% と Turn Time\n" % ven)
        for k in sorted(D, key=int):
            v = D[k]
            if only and v["R"] not in only:
                continue
            fs, tt = race_fs(v)
            if fs is None:
                print("%2dR ダ%dm  ラップが足りない" % (v["R"], v["dist"])); continue
            c, src = sui(ven, v["dist"], v["baba"])
            d1 = "（水準%+.1f）" % (fs - c["fs"]) if c else ""
            d2 = "（水準%+.1f）" % (tt - c["tt"]) if c else ""
            win = [r for r in v["rows"] if r["chaku"] == 1][0]
            print("%2dR ダ%4dm %s %2d頭 │ FS%% %5.1f%s │ TT %4.1f秒%s │ 1着 %s %d人気 4角%s" % (
                v["R"], v["dist"], v["baba"], len(v["rows"]), fs, d1, tt, d2,
                w(win["name"], 14), win["nk"], win.get("c4")))
        return
    if "--card" in a:
        D = json.load(open(a[a.index("--card") + 1]))
        R = int(a[a.index("--R") + 1]) if "--R" in a else None
        q = [x for x in a if not x.startswith("--") and not x.endswith(".json") and not x.isdigit()]
        q = q[0] if q else None
        for k in sorted(D, key=int):
            v = D[k]
            if R and v["R"] != R:
                continue
            hs = [h for h in v["horses"] if (q is None or q in h["name"])]
            if not hs:
                continue
            print("\n%2dR ダ%4dm %2d頭  %s" % (v["R"], v["dist"], len(v["horses"]),
                                              (v.get("cls") or "")[:20]))
            for h in hs:
                vals = []
                for p in (h.get("past") or []):
                    fs = horse_fs(p.get("t"), p.get("agari"), p["dist"])
                    if fs is None:
                        continue
                    c, _ = sui(p["venue"], p["dist"], p["baba"])
                    vals.append((p, fs, (fs - c["fs"]) if c else None))
                if not vals:
                    print("  %2d %s  測れない" % (h["ub"], w(h["name"], 15))); continue
                diffs = [x[2] for x in vals if x[2] is not None]
                med = st.median([x[1] for x in vals])
                print("  %2d %s %s枠  FS%% 中央値 %.1f%s" % (
                    h["ub"], w(h["name"], 15), h.get("waku"), med,
                    "  水準比 中央値 %+.1f" % st.median(diffs) if diffs else ""))
                if q:
                    for p, fs, df in vals:
                        print("      %s %s %s %4dm %2d頭 %2d人 %2d着  FS%% %5.1f%s" % (
                            p["date"], p["venue"], p["baba"], p["dist"], p["n"],
                            p["nk"], p["chaku"], fs,
                            "（水準%+.1f）" % df if df is not None else "（水準なし）"))
        return
    print(__doc__)


if __name__ == "__main__":
    main()
