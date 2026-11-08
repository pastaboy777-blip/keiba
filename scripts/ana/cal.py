"""南関4場の開催カレンダーを作る ── 日付 → base16（harvest.py に渡す16桁）。

  python3 cal.py --scan 20260101 20261108    # その範囲を走査して cal.json に足す
  python3 cal.py --list                      # 取れているものを場ごとに出す
  python3 cal.py --todo                      # まだ harvest していない日を出す

── ★ 日付の一覧ページに RACEID が入っている

  https://keiba.rakuten.co.jp/race_card/list/RACEID/<日付8桁>0000000000

  このページの本文に、その日の各場の RACEID が 18桁で埋まっている。

    202611082135090100
    └日付8─┘└場┘└中間┘└回┘└日┘└R┘

  base16 = 先頭16桁。R の2桁を付け替えれば各レースになる。
  **総当たりで回・日を探す必要はない。**

  場 … 18浦和 19船橋 20大井 21川崎（他場も出るが南関だけ拾う）
"""
import sys, os, json, re, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harvest as H

CAL = os.path.join(HERE, "cal.json")
JYO = {"18": "ura", "19": "fun", "20": "ooi", "21": "kaw"}
SLEEP = 3.0


def load():
    return json.load(open(CAL)) if os.path.exists(CAL) else {}


def scan(d0, d1):
    import datetime as dt
    C = load()
    a = dt.date(int(d0[:4]), int(d0[4:6]), int(d0[6:]))
    b = dt.date(int(d1[:4]), int(d1[4:6]), int(d1[6:]))
    n = 0
    while a <= b:
        key = a.strftime("%Y%m%d")
        if key in C:
            a += dt.timedelta(days=1); continue
        t = H.rk("https://keiba.rakuten.co.jp/race_card/list/RACEID/%s0000000000" % key)
        found = {}
        for rid in set(re.findall(r"(%s\d{10})" % key, t)):
            jy = rid[8:10]
            if jy in JYO and rid[16:18] != "00" or jy in JYO:
                found[JYO[jy]] = rid[:16]
        C[key] = found
        n += 1
        if found:
            print("%s  %s" % (key, " ".join("%s:%s" % (k, v) for k, v in sorted(found.items()))), flush=True)
        json.dump(C, open(CAL, "w"), ensure_ascii=False, indent=0, sort_keys=True)
        a += dt.timedelta(days=1)
        time.sleep(SLEEP)
    print("\n走査 %d日 ／ 開催のあった日 %d" % (n, sum(1 for v in C.values() if v)))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    if "--scan" in a:
        i = a.index("--scan")
        scan(a[i + 1], a[i + 2]); return
    C = load()
    if "--list" in a:
        import collections
        c = collections.defaultdict(list)
        for d in sorted(C):
            for v, b in C[d].items():
                c[v].append(d)
        for v in ("ooi", "fun", "ura", "kaw"):
            print("%s %3d日  %s … %s" % (v, len(c[v]), c[v][0] if c[v] else "-",
                                         c[v][-1] if c[v] else "-"))
        return
    if "--todo" in a:
        import glob
        done = {os.path.basename(f)[:3] + os.path.basename(f)[3:7]
                for f in glob.glob(os.path.join(HERE, "harvest", "*_res.json"))}
        todo = []
        for d in sorted(C):
            for v, b in C[d].items():
                if v + d[4:8] not in done:
                    todo.append((d, v, b))
        print("未取得 %d日ぶん" % len(todo))
        for d, v, b in todo[:40]:
            print("   %s %s %s" % (d, v, b))
        return
    print(__doc__)


if __name__ == "__main__":
    main()
