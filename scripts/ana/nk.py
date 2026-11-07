"""netkeiba から中央（JRA）の出馬表・結果を取る。地方ツールしか無かったので足した。

  python3 nk.py card <race_id>     # 出馬表（枠・馬番・馬名・性齢・斤量・騎手・厩舎）
  python3 nk.py res  <race_id>     # 結果（着順・馬番・馬名・斤量・騎手・タイム・着差・人気・上がり・通過）
  python3 nk.py day  <YYYYMMDD>    # その日の全レースIDを総当たりで探す

── race_id の作り

  年4 + 場2 + 回2 + 日2 + R2

  場 … 01札幌 02函館 03福島 04新潟 05東京 06中山 07中京 08京都 09阪神 10小倉

  例  202605050211 = 2026年 東京 5回 2日目 11R（アルゼンチン共和国杯）

── ★ このセッションで通るホスト

  race.netkeiba.com と db.netkeiba.com は通る。
  jra.go.jp / sports.yahoo.co.jp / keibalab.jp / winsight.jp / umanity.jp は
  ネットワーク設定で塞がれていて開けない（2026-11-07 時点）。

── ★ 出馬表ページは JavaScript 無しでも中身が入っている

  race_list.html（日付の一覧）だけは JS で描くので空で返る。
  そのため `day` は一覧を読まず、R を 1〜12 で総当たりして開く。
"""
import sys, re, subprocess

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
JYO = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
       "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}


def get(url):
    r = subprocess.run(["curl", "-sS", "--max-time", "30", "-A", UA, url], capture_output=True)
    return r.stdout.decode("utf-8", "replace")


def flat(h):
    h = re.sub(r"<script.*?</script>", " ", h, flags=re.S)
    h = re.sub(r"<style.*?</style>", " ", h, flags=re.S)
    # ★ &nbsp; を空白に。落とさないと馬柱の列が繋がったまま読めない（一度ここで躓いた）
    h = h.replace("&nbsp;", " ").replace("&amp;nbsp;", " ")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))


def head(t):
    """レース名・距離・馬場・発走などの見出し"""
    m = re.search(r"(\d+R) ([^ ]+) (\d+:\d+)発走 .{0,40}?(芝|ダ)(\d+)m ([左右]?)\s*(\S*?) ?/ ?(?:予報 )?(\S+) ?/ ?(\S+)", t)
    d = {}
    if m:
        d = {"R": m.group(1), "name": m.group(2), "start": m.group(3),
             "sur": m.group(4), "dist": int(m.group(5)), "baba": m.group(8), "wind": m.group(9)}
    m2 = re.search(r"(\d)回 (\S+) (\d+)日目", t)
    if m2:
        d["kai"], d["jyo"], d["nichi"] = m2.group(1), m2.group(2), m2.group(3)
    return d


ROW_CARD = re.compile(
    r"(?<![\d.])(\d{1,2}) (\d{1,2}) -- ◎ ◯ ▲ △ ☆ &amp;#10003 消 "
    r"([ァ-ヶー]{2,}) ([牡牝セ]\d+) ([\d.]+) (\S+) (美浦|栗東|地方|海外) (\S+)")


def card(rid):
    t = flat(get("https://race.netkeiba.com/race/shutuba.html?race_id=" + rid))
    out = []
    for m in ROW_CARD.finditer(t):
        out.append({"waku": int(m.group(1)), "ub": int(m.group(2)), "name": m.group(3),
                    "sex": m.group(4), "kin": float(m.group(5)), "jk": m.group(6),
                    "belong": m.group(7), "tr": m.group(8)})
    # 馬番の重複を落とす（同じ行が二度出ることがある）
    seen, uniq = set(), []
    for r in out:
        if r["ub"] in seen:
            continue
        seen.add(r["ub"]); uniq.append(r)
    return head(t), sorted(uniq, key=lambda r: r["ub"])


# 列は 着順 枠 馬番 馬名 性齢 斤量 騎手 タイム [着差] 人気 単勝 後3F [通過順] 所属 厩舎 馬体重(増減)
# ★ 1着は着差が空、通過順はレースによって無い。真ん中はまとめて拾って後で分ける。
ROW_RES = re.compile(
    r"(?<![\d.])(\d{1,2}) (\d{1,2}) (\d{1,2}) ([ァ-ヶー]{2,}) ([牡牝セ]\d+) ([\d.]+) (\S+) "
    r"(\d+:\d+\.\d)((?: [^ ]+)*?) (美浦|栗東|地方|海外) (\S+) (\d{3}) \(([^)]*)\)")


def split_mid(toks):
    """タイムと所属のあいだ … [着差…] 人気 単勝 後3F [通過順…]

    ★ 人気は 1〜18 の整数。**最初に現れる整数**が人気で、その手前が着差。
      着差は「ハナ」「1.1/4」など整数にならないので、これで切れる。
    """
    # ★ 着差が「2」のような裸の数字のことがあり、人気と取り違える。
    #   だから単独で探さず、**人気・単勝・後3F の3つ並びが成立する位置**を探す。
    #   後3F は必ず2桁.1桁（30〜49秒台）なので、ここが錨になる。
    def ok(k):
        if k + 2 >= len(toks) + 0 or k + 2 > len(toks) - 1:
            return False
        a, b, c = toks[k], toks[k + 1], toks[k + 2]
        if not (a.isdigit() and 1 <= int(a) <= 18):
            return False
        if not re.match(r"^\d{2}\.\d$", c):
            return False
        try:
            float(b)
        except ValueError:
            return False
        return 29.0 < float(c) < 50.0

    i = next((k for k in range(len(toks)) if ok(k)), None)
    if i is None:
        return None
    sa = " ".join(toks[:i]) or None
    nk = int(toks[i]); odds = toks[i + 1]; ag = toks[i + 2]
    ts = [int(x) for x in re.findall(r"\d+", " ".join(toks[i + 3:]))]
    try:
        return {"sa": sa, "nk": nk, "odds": float(odds), "agari": float(ag), "tsuka": ts}
    except ValueError:
        return None


def laps(t):
    """結果ページの「ラップタイム」欄。

    ペース: H（ハイ）/ M（平均）/ S（スロー）のあと、
    **200mごとの累計**が並び、そのあとに**200mごとの区間**が並ぶ。
    欲しいのは後ろの区間のほう。
    """
    m = re.search(r"ラップタイム ペース: (\S+)(.*?)(?:ひとこと|※結果)", t)
    if not m:
        return None, []
    nums = re.findall(r"\d+:\d\d\.\d|\d\d?\.\d", m.group(2))
    # ★ 累計と区間は**同じ本数**。だから全体の後ろ半分がそのまま区間になる。
    #   累計だけ「1:12.4」と分を含むので、":" で選り分けると数が合わなくなる（一度間違えた）。
    half = nums[len(nums) // 2:]
    return m.group(1), [float(x) for x in half if ":" not in x]


def res(rid):
    t = flat(get("https://race.netkeiba.com/race/result.html?race_id=" + rid))
    out, seen = [], set()
    for m in ROW_RES.finditer(t):
        mid = split_mid(m.group(9).split())
        if not mid or int(m.group(1)) in seen:
            continue
        seen.add(int(m.group(1)))
        r = {"chaku": int(m.group(1)), "waku": int(m.group(2)), "ub": int(m.group(3)),
             "name": m.group(4), "sex": m.group(5), "kin": float(m.group(6)),
             "jk": m.group(7), "time": m.group(8), "belong": m.group(10), "tr": m.group(11),
             "w": int(m.group(12)), "dw": m.group(13)}
        r.update(mid)
        out.append(r)
    pace, lp = laps(t)
    h = head(t); h["pace"], h["lap"] = pace, lp
    return h, sorted(out, key=lambda r: r["chaku"])


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return
    cmd = a[0]
    if cmd == "card":
        h, rs = card(a[1])
        print(h)
        for r in rs:
            print("  %d枠 %2d番 %-16s %s %4.1f %-7s %s %s" % (
                r["waku"], r["ub"], r["name"], r["sex"], r["kin"], r["jk"], r["belong"], r["tr"]))
    elif cmd == "res":
        h, rs = res(a[1])
        print(h)
        for r in rs:
            print("  %2d着 %d枠 %2d番 %-16s %4.1f %-7s %7s %-5s %2d人 %6.1f倍 通過%-12s 上%.1f" % (
                r["chaku"], r["waku"], r["ub"], r["name"], r["kin"], r["jk"], r["time"],
                r["sa"], r["nk"], r["odds"], "-".join(map(str, r["tsuka"])), r["agari"]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()


# ── 馬柱つき出馬表（shutuba_past.html）─────────────────────────
# 1頭ぶん … <父> <馬名> <母> (<母父>) <厩舎> <脚質> 中N週 … <性齢毛> <騎手> <斤量> + 過去走
# 過去走 … 日付 場 着順 クラス 芝/ダ距離 タイム 馬場 頭数 馬番 人気 騎手 斤量 通過順 (上がり) 馬体重(増減) 1着馬 (着差)
PAST = re.compile(
    r"(\d{4}\.\d\d\.\d\d) (\S+?) (\d{1,2}) .{0,24}? (芝|ダ)(\d{3,4}) (\d+:\d+\.\d) (\S) "
    r"(\d+)頭 (\d+)番 (\d+)人 \S+ [\d.]+ ([\d\-]+) \(([\d.]+)\) (\d{3})\(([+\-]?\d+)\) \S+ \(([\d.]+)\)")

HEAD_P = re.compile(
    r"消 (\S+) ([ァ-ヶーA-Za-z]{2,}) (\S+) \(([^)]+)\) (美浦|栗東)・(\S+) +(逃|先|差|追|自)? ?中?(\d+)?週?")


def past_card(rid):
    """馬柱つき出馬表。{馬番: {...}} ではなく並び順のリストで返す"""
    import subprocess as sp
    b = sp.run(["curl", "-sS", "--max-time", "40", "-A", UA,
                "https://race.netkeiba.com/race/shutuba_past.html?race_id=" + rid],
               capture_output=True).stdout
    t = flat(b.decode("utf-8", "replace"))
    hd = head(t)
    out = []
    for chunk in t.split("消 ")[1:]:
        m = HEAD_P.match("消 " + chunk[:260])
        if not m:
            continue
        runs = []
        for p in PAST.finditer(chunk[:4000]):
            ts = [int(x) for x in p.group(11).split("-") if x.isdigit()]
            runs.append({"date": p.group(1), "jyo": p.group(2), "chaku": int(p.group(3)),
                         "sur": p.group(4), "dist": int(p.group(5)), "time": p.group(6),
                         "baba": p.group(7), "n": int(p.group(8)), "ub": int(p.group(9)),
                         "nk": int(p.group(10)), "tsuka": ts, "agari": float(p.group(12)),
                         "w": int(p.group(13)), "dw": int(p.group(14)), "sa": float(p.group(15))})
        out.append({"f": m.group(1), "name": m.group(2), "m": m.group(3), "mf": m.group(4),
                    "belong": m.group(5), "tr": m.group(6), "kyaku": m.group(7),
                    "weeks": m.group(8), "runs": runs})
    return hd, out
