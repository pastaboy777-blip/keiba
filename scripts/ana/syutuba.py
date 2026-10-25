"""楽天の出馬表を、過去5走ぶんそろえて構造化する ── ログイン不要。

  python3 syutuba.py <base16> <出力.json> [--R 1-12]

base16 は楽天の RACEID の頭16桁。その日の一覧から拾う。

  https://keiba.rakuten.co.jp/race_card/list/RACEID/<日付8桁>0000000000

  例  2026102620151101  = 2026/10/26 大井（場20・第11回・第1日）
      2026102318130705  = 2026/10/23 浦和（場18・第7回・第5日）

場コード … 浦和18 / 船橋19 / 大井20 / 川崎21 / 笠松23 / 園田27 / 門別36

── 取れるもの

  鞍ごと … R・距離・発走時刻・クラス
  馬ごと … 馬番・枠・馬名・過去5走
  過去走 … 着順・馬場・頭数・場・日付・距離・芝ダ・人気・斤量・着差・
           上がり3F・馬体重・そのときの枠・通過順（c1 と c4 つき）

── ★ 当日に取り直すこと（CLAUDE.md ルール3）

  **馬体重と増減とオッズと人気は、前日は空で、当日に入る。**
  前日に作るカードは下見。**発走30分前に取り直して印を打ち直す**のが本来の形。
  この取得そのものは何度走らせても同じ形で返るので、当日そのまま上書きしてよい。

── ★ 通過順は楽天ならマスクされない（2026-10-24に確認）

  競馬ブックは cookie が切れると通過順もラップも **** になる。
  楽天は19日前のレースでも括弧つきの生の形で残っていた。
  ルール5「通過順は開催当日に取る」は競馬ブックの話で、楽天には当てはまらない。
"""
import re, sys, json, time, subprocess

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
SLEEP = 1.2

# 着順 馬場 頭数 過去映像 場 日付 レース名 クラス 距離 人気 騎手 斤量 タイム (着差) 上3F 馬体重 枠 通過順
PAST = re.compile(
    r"(\d{1,2})\s+(良|稍|重|不)\s+(\d{1,2})頭\s+過去映像\s+(\S+?)\s+"
    r"(\d\d\.\d\d\.\d\d)\s+.{0,40}?(\d{3,4})\s*(?:左|右|直)?\s*(ダ|芝)\s+"
    r"(\d{1,2})人\s+\S{1,8}?\s*([\d.]+)\s+([\d:.]+)\s*\(([\d.]+)\)\s+"
    r"([\d.]+)\s+(\d+)k\s+(\d+)番\s+([\d\-]+)")


class Blocked(Exception):
    pass


def get(u):
    """★ 0字（通信落ち）と短いスタブ（絞り）は別物。前者だけリトライする"""
    for wait in (4, 12, None):
        r = subprocess.run(["curl", "-sS", "--max-time", "45", "-A", UA, u],
                           capture_output=True, timeout=70)
        h = r.stdout.decode("utf-8", "replace")
        if len(h) >= 20000:
            return h
        if len(h) > 0 or wait is None:
            break
        time.sleep(wait)
    raise Blocked("楽天が %d字 を返しました。%s" % (
        len(h), "通信が続けて落ちました" if not h else
                "スタブです（絞られています）。時間を空けてください"))


def flat(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


def one(base, R):
    h = get(CARD + "%s%02d" % (base, R))
    t = flat(h)
    md = re.search(r"(ダ|芝)([\d,]+)m", t)
    ms = re.search(r"発走時刻\s*(\d+:\d\d)\s+(\S+)", t)
    pos = [m.start() for m in re.finditer(r'class="number"', h)]
    hs = []
    for i, p in enumerate(pos):
        blk = h[p:pos[i + 1] if i + 1 < len(pos) else len(h)]
        mu = re.match(r'class="number"[^>]*>\s*(\d+)', blk)
        # 枠は馬番セルの手前の class="position"
        mw = re.findall(r'class="position"[^>]*>\s*(\d+)', h[:p])
        mn = re.search(r'class="mainHorse"[^>]*>\s*<a[^>]*>([^<]+)</a>', blk)
        if not (mu and mn):
            continue
        fb = flat(blk)
        runs = []
        for m in PAST.finditer(fb):
            (ch, baba, n, ven, dt, dist, sur, nk, kin, tm, sa, ag, w, wk, ts) = m.groups()
            q = [int(y) for y in ts.split("-") if y.isdigit()]
            runs.append({"chaku": int(ch), "baba": baba, "n": int(n), "venue": ven,
                         "date": dt, "dist": int(dist), "sur": sur, "nk": int(nk),
                         "kin": float(kin), "sa": float(sa), "agari": float(ag),
                         "w": int(w), "waku": int(wk), "tsuka": q,
                         "c1": q[0] if q else None, "c4": q[-1] if q else None})
        # ★ 当日だけ入る欄。前日は空
        mo = re.search(r"(\d+\.\d)\s*倍", fb)
        mnk = re.search(r"(\d{1,2})\s*番人気", fb)
        mww = re.search(r"\s(\d{3})k?\s*[（(]\s*([-+±]?\d+)\s*[）)]", fb)
        hs.append({"ub": int(mu.group(1)), "waku": int(mw[-1]) if mw else None,
                   "name": mn.group(1).strip(), "past": runs,
                   "odds": float(mo.group(1)) if mo else None,
                   "nin": int(mnk.group(1)) if mnk else None,
                   "w": int(mww.group(1)) if mww else None,
                   "dw": mww.group(2).replace("±", "+") if mww else None})
    return {"R": R, "dist": int(md.group(2).replace(",", "")) if md else None,
            "start": ms.group(1) if ms else "", "cls": ms.group(2) if ms else "",
            "horses": hs}


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__); return
    base, out = a[0], a[1]
    rr = range(1, 13)
    if "--R" in a:
        v = a[a.index("--R") + 1]
        lo, _, hi = v.partition("-")
        rr = range(int(lo), int(hi or lo) + 1)
    store = {}
    try:
        for R in rr:
            v = one(base, R)
            if not v["horses"]:
                print("%2dR なし" % R, flush=True); continue
            store[str(R)] = v
            nw = sum(1 for x in v["horses"] if x["w"])
            print("%2dR %4dm %-16s %2d頭  過去走%3d本  馬体重%s" % (
                R, v["dist"] or 0, v["cls"][:16], len(v["horses"]),
                sum(len(x["past"]) for x in v["horses"]),
                "%d頭" % nw if nw else "まだ空"), flush=True)
            json.dump(store, open(out, "w"), ensure_ascii=False)
            time.sleep(SLEEP)
    except Blocked as e:
        print("\n★ 止めました:", e)
        print("  粘らないこと。時間を空けてやり直す。")
        json.dump(store, open(out, "w"), ensure_ascii=False)
        sys.exit(1)
    print("\n%d鞍 / %d頭 → %s" % (
        len(store), sum(len(v["horses"]) for v in store.values()), out))


if __name__ == "__main__":
    main()
