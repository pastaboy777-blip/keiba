"""大井だけ・過去3年ぶんの結果（展開隊列図の元データ）を集める。

  python3 ooi3y.py --scan 20231127 20261126   # 日付ごとに楽天の一覧を見て大井の base16 を拾う
  python3 ooi3y.py --harvest [--max N]        # 拾った日の結果を古い順に取る（1日ずつ）
  python3 ooi3y.py --stat                     # どこまで進んだか

★ 2026-11-26、ユーザーの指示 ──「過去3年分　大井競馬の展開隊列図　データ取って！」「大井競馬だけ！」

★ 置き場所は **harvest_ooi3y/**（harvest/ とは別）。
  - harvest/ のラベルは「場+MMDD」で、3年ぶん入れると年が違う同じ日付がぶつかる。
    ここでは **ooiYYYYMMDD** にする。
  - harvest/ に足すと toki.json / soto.json / jk_soto.json の --build の母数が変わり、
    いまの図の出力が変わる（ルール38）。**混ぜるかどうかはユーザーが決める。**
  - 取り方・中身の形は harvest.py の do_res と**まったく同じ**（DATA だけ差し替えて呼ぶ）。

★ 楽天に絞られたら harvest.py が Blocked で止まる。粘らない。数時間空けて続きから。
"""
import os, sys, re, json, time, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harvest as H

OUT = os.path.join(HERE, "harvest_ooi3y")
CAL = os.path.join(OUT, "cal.json")
SLEEP = 3.0
MIN_R = 8

os.makedirs(OUT, exist_ok=True)
H.DATA = OUT          # do_res の保存先だけ差し替える


def load_cal():
    return json.load(open(CAL)) if os.path.exists(CAL) else {}


def scan(d0, d1):
    C = load_cal()
    a = dt.date(int(d0[:4]), int(d0[4:6]), int(d0[6:]))
    b = dt.date(int(d1[:4]), int(d1[4:6]), int(d1[6:]))
    while a <= b:
        key = a.strftime("%Y%m%d")
        if key not in C:
            t = H.rk("https://keiba.rakuten.co.jp/race_card/list/RACEID/%s0000000000" % key)
            ids = {r[:16] for r in re.findall(r"(%s20\d{8})" % key, t)}
            C[key] = sorted(ids)[0] if ids else ""
            if C[key]:
                print(key, C[key], flush=True)
            json.dump(C, open(CAL, "w"), indent=0, sort_keys=True)
            time.sleep(SLEEP)
        a += dt.timedelta(days=1)
    print("走査ずみ %d日 ／ 大井の開催日 %d" % (len(C), sum(1 for v in C.values() if v)))


def n_res(label):
    p = os.path.join(OUT, "%s_res.json" % label)
    try:
        return len(json.load(open(p)))
    except Exception:
        return 0


def todo():
    C = load_cal()
    return [(d, b) for d, b in sorted(C.items()) if b and n_res("ooi" + d) < MIN_R]


def harvest(mx=None):
    T = todo()[:mx] if mx else todo()
    print("大井 … %d日ぶん" % len(T), flush=True)
    for i, (d, b) in enumerate(T, 1):
        print("\n[%d/%d] %s %s" % (i, len(T), d, b), flush=True)
        try:
            H.do_res(b, "ooi" + d)
        except H.Blocked as e:
            print("\n★ 止めました（絞られている可能性）:", e, flush=True)
            sys.exit(1)
    print("\n残り %d日" % len(todo()), flush=True)


def stat():
    C = load_cal()
    days = [d for d, b in C.items() if b]
    got = [d for d in days if n_res("ooi" + d) >= MIN_R]
    print("走査 %d日（%s … %s）／ 大井の開催日 %d ／ 取得ずみ %d日・%d鞍" % (
        len(C), min(C) if C else "-", max(C) if C else "-", len(days), len(got),
        sum(n_res("ooi" + d) for d in days)))


def main():
    a = sys.argv[1:]
    if "--scan" in a:
        i = a.index("--scan"); scan(a[i + 1], a[i + 2])
    elif "--harvest" in a:
        harvest(int(a[a.index("--max") + 1]) if "--max" in a else None)
    elif "--stat" in a:
        stat()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
