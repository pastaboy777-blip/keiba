"""南関4場の開催カレンダーを作る ── 日付 → base16（harvest.py に渡す16桁）。

  python3 cal.py --scan 20260101 20261108    # その範囲を走査して cal.json に足す
  python3 cal.py --list                      # 取れているものを場ごとに出す
  python3 cal.py --todo                      # まだ harvest していない日を出す
  python3 cal.py --harvest fun               # 未取得の船橋を古い順に取る（1日ずつ）
  python3 cal.py --harvest fun --max 10      # 10日だけ
  python3 cal.py --harvest ooi --upgrade     # 古い形で入っている日も取り直す

── ★ --upgrade は「古い形の日」を拾い直す

  corner_raw（通過順の記号）・t（走破タイム）・sa（着差）は後から足した。
  それ以前に取った日はこの3つを持っていない。
  harvest.py do_res は corner_raw の無い鞍だけ取り直すので、足りない分だけ埋まる。

── ★ --harvest は絞られたら**その場で止まる**

  harvest.py は楽天が短いページを返した時点で exit 1 する。
  それを見たらループを抜ける。**粘らない。数時間空ける。**
  resumable なので、空けてからもう一度叩けば続きから積む。

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


MIN_R = 10      # これ未満の鞍数しか入っていない日は「途中で止まった」とみなす


def done_set():
    """harvest/ に既にある「場+MMDD」。

    ★ ファイル名は ooi1004 / ooiL0112 / ooi1026res とばらばら。
      場3文字のあと**最初に出る4桁**を MMDD とみなす。
      単純に [3:7] で切ると ooiL0112 が「ooiL011」になって一件も当たらない
      （実際にそれで大井81日ぶんを「未取得」と誤って出した）。

    ★ ファイルがあるだけでは「取得ずみ」にしない。
      南関は1日10〜12鞍。3鞍しか入っていない日は、途中で止めたか、
      開催中に取ったまま（11/4がそれ）。**ファイルの有無だけで判定すると
      永久に穴が埋まらない。**harvest.py は鞍ごとに積むので、
      もう一度 res を叩けば足りない鞍だけ埋まる。"""
    import glob, json as J
    s = set()
    for f in glob.glob(os.path.join(HERE, "harvest", "*_res.json")):
        b = os.path.basename(f)
        m = re.search(r"(\d{4})", b[3:])
        if not m:
            continue
        try:
            if len(J.load(open(f))) < MIN_R:
                continue
        except Exception:
            continue
        s.add(b[:3] + m.group(1))
    return s


def is_new(label):
    """最新の形（corner_raw・t・sa つき）で入っているか。
    corner_raw は通過順の**記号**（( ) 横並び／, 1馬身以内／- 1〜2馬身／= 大きく開いた）。
    古いファイルは corner しか無く、着差の目安が読めない。"""
    import json as J
    f = os.path.join(HERE, "harvest", "%s_res.json" % label)
    if not os.path.exists(f):
        return False
    try:
        D = J.load(open(f))
    except Exception:
        return False
    if len(D) < MIN_R:
        return False
    return all(v.get("corner_raw") is not None for v in D.values())


def todo_list(ven=None, upgrade=False):
    """upgrade=True … 古い形で入っている日も「やること」に入れる。
    harvest.py do_res は corner_raw の無い鞍だけ取り直すので、
    足りないところだけ埋まる。"""
    C, done = load(), done_set()
    out = []
    for d in sorted(C):
        for v, b in sorted(C[d].items()):
            if ven and v != ven:
                continue
            label = v + d[4:8]
            if label not in done or (upgrade and not is_new(label)):
                out.append((d, v, b))
    return out


def harvest(ven, mx=None, upgrade=False):
    """未取得の日を古い順に harvest.py res に渡す。絞られたら止める。"""
    import subprocess
    T = todo_list(ven, upgrade)
    if mx:
        T = T[:mx]
    print("%s … %d日ぶん" % (ven, len(T)), flush=True)
    ok = ng = 0
    for i, (d, v, b) in enumerate(T, 1):
        label = v + d[4:8]
        print("\n[%d/%d] %s %s %s" % (i, len(T), d, label, b), flush=True)
        r = subprocess.run([sys.executable, os.path.join(HERE, "harvest.py"),
                            "res", b, label])
        if r.returncode != 0:
            print("\n★ %s で止まりました。絞られている可能性。"
                  "数時間空けて harvest.py check からやり直すこと。" % label, flush=True)
            ng += 1
            break
        ok += 1
    print("\n取れた %d日 ／ 残り %d日" % (ok, len(todo_list(ven, upgrade))), flush=True)


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    if "--scan" in a:
        i = a.index("--scan")
        scan(a[i + 1], a[i + 2]); return
    if "--harvest" in a:
        v = a[a.index("--harvest") + 1]
        mx = int(a[a.index("--max") + 1]) if "--max" in a else None
        harvest(v, mx, "--upgrade" in a); return
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
        import collections
        done = done_set()
        hv = collections.Counter(); tv = collections.Counter()
        for d in sorted(C):
            for v, b in C[d].items():
                (hv if v + d[4:8] in done else tv)[v] += 1
        print("場   取得ずみ 未取得")
        for v in ("ooi", "fun", "kaw", "ura"):
            print("  %s  %5d %6d" % (v, hv[v], tv[v]))
        t = todo_list()
        print("\n未取得 計 %d日（4秒間隔・1日12鞍で約 %.1f時間）" % (
            len(t), len(t) * 12 * 4 / 3600))
        for d, v, b in t[:20]:
            print("   %s %s %s" % (d, v, b))
        return
    print(__doc__)


if __name__ == "__main__":
    main()
