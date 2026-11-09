"""「変化」で穴を探す ── 前走から場が替わって、距離も変わった馬を出馬表から拾う。

  python3 henka.py 2026 10 23 18          # 年 月 日 場コード（浦和18 川崎21 船橋19 大井20）
  python3 henka.py 2026 10 23 18 --all    # 該当しない馬も全部出す

楽天の出馬表（race_card）から各馬の前走を読む。会員登録もcookieも要らない。

── なぜこの2つなのか（2026-10-19〜22 の浦和4日・45鞍・496頭で測った）

6人気以下の275頭を、前走からの変化で割ると

    場替わり＋距離も変化   98頭  6勝(6.1%)  3着内16.3%
    場替わりのみ           10頭  0勝        3着内10.0%
    距離変化のみ           68頭  0勝        3着内10.3%
    前走も同じ場＋同距離    99頭  1勝(1.0%)  3着内 5.1%

人気薄全体の3着内率が10.5%なので、この形で16.3%、外すと5.1%。
**人気薄で勝った7頭のうち6頭がこの形**だった。しかも平均人気は9.0と8.6で
ほとんど変わらないので、オッズには入っていない。

前走の着差は「3.1秒以上は落とす」だけに使う（66頭で3着内7.6%）。
10/22の1日だけだと「前走1.6〜3.0秒差」が強く見えたが、4日に広げると
1.5秒差以内(11.5%)とほぼ同じになって消えた。10/20・10/21の穴の勝ち馬は
前走0.9〜5.1秒差とバラバラで、共通していたのは場と距離の変化のほうだった。

1開催ぶんの話。浦和は南関の他場から転戦してくる馬が多い場なので、
別の場で同じに出るとは限らない。
"""
import re, os, sys, json, time, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = "https://keiba.rakuten.co.jp/"
CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/"
JYO = {"18": "浦和", "19": "船橋", "20": "大井", "21": "川崎",
       "23": "笠松", "27": "園田", "36": "門別"}
SA_MAX = 3.0            # 前走でこれ以上離されていたら落とす（力が足りないだけ）


def get(u):
    for i in range(4):
        r = subprocess.run(["curl", "-sS", "--max-time", "45", "-A", "Mozilla/5.0", u],
                           capture_output=True)
        if r.returncode == 0 and len(r.stdout) > 5000:
            return r.stdout.decode("utf-8", "replace")
        time.sleep(2 * (i + 1))
    return ""


def flat(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


def base_id(y, m, d, jyo):
    key = "%04d%02d%02d%02d" % (y, m, d, jyo)
    for rid in re.findall(r"race_card/list/RACEID/(\d{18})", get(TOP)):
        if rid.startswith(key):
            return rid[:16]
    return None


# 「7 不 10頭 過去映像 大井 26.09.15 マイルグラン Ａ２ 内1600右ダ 9人 ▲西優哉
#   52.0 1:42.4 (2.0) 38.9 457k 9番 7-7-7-7 スマイルマン」
PAST = re.compile(
    r"(\d{1,2})\s+(良|稍|重|不)\s+(\d{1,2})頭\s+過去映像\s+(\S+?)\s+"
    r"(\d\d\.\d\d\.\d\d)\s+.{0,40}?(\d{3,4})\s*(?:左|右|直)?\s*(ダ|芝)\s+"
    r"(\d{1,2})人\s+\S{1,8}?\s*[\d.]+\s+[\d:.]+\s*\(([\d.]+)\)")


def horses(h):
    """出馬表のHTMLから {ub, name, past} を並べて返す"""
    pos = [m.start() for m in re.finditer(r'class="number"', h)]
    out = []
    for i, p in enumerate(pos):
        blk = h[p:pos[i + 1] if i + 1 < len(pos) else len(h)]
        mu = re.match(r'class="number"[^>]*>\s*(\d+)', blk)
        mn = re.search(r'class="mainHorse"[^>]*>\s*<a[^>]*>([^<]+)</a>', blk)
        if not (mu and mn):
            continue
        m = PAST.search(flat(blk))
        p0 = None
        if m:
            ch, baba, n, ven, dt, dist, sur, nk, sa = m.groups()
            p0 = {"chaku": int(ch), "baba": baba, "n": int(n), "venue": ven,
                  "date": dt, "dist": int(dist), "sur": sur,
                  "nk": int(nk), "sa": float(sa)}
        out.append({"ub": int(mu.group(1)), "name": mn.group(1).strip(), "past": p0})
    return out


def judge(z, track, dist):
    """変化の判定。前走が引けない馬は除外ではなく『?』にする（CLAUDE.md ルール6）"""
    p = z.get("past")
    if not p:
        return "?", "前走が引けません（転入初戦など）。弱いという意味ではない"
    chg_v = p["venue"] != track
    chg_d = p["dist"] != dist
    far = p["chaku"] >= 2 and p["sa"] > SA_MAX
    note = "前走 %s%dm %d着 %.1f差（%d頭立て %d人気）→ 今日 %s%dm（%+dm）" % (
        p["venue"], p["dist"], p["chaku"], p["sa"], p["n"], p["nk"],
        track, dist, dist - p["dist"])
    if far:
        return "×", note + "／前走で%.1f秒離されている" % p["sa"]
    if chg_v and chg_d:
        return "◎", note
    if chg_v or chg_d:
        return "△", note
    return "・", note


def main():
    if len(sys.argv) < 5:
        print(__doc__); return
    y, mo, d, jy = (int(x) for x in sys.argv[1:5])
    track = JYO.get("%02d" % jy, "?")
    bid = base_id(y, mo, d, jy)
    if not bid:
        print("トップページにその日・その場のレースがありません。開催日を確認してください。")
        return
    allmode = "--all" in sys.argv
    print("%04d/%02d/%02d %s（RACEID の頭 %s）" % (y, mo, d, track, bid))
    print("◎=場も距離も変わった　△=どちらか片方　・=前走も同じ場＋同距離　"
          "×=前走で%.1f秒以上離された　?=前走が引けない\n" % SA_MAX)
    tot = {"◎": 0, "△": 0, "・": 0, "×": 0, "?": 0}
    for R in range(1, 13):
        h = get(CARD + "%s%02d" % (bid, R))
        if not h:
            print("%2dR 取れませんでした" % R); continue
        t = flat(h)
        md = re.search(r"(ダ|芝)([\d,]+)m", t)
        dist = int(md.group(2).replace(",", "")) if md else None
        ms = re.search(r"発走時刻\s*(\d+:\d\d)\s+(\S+)", t)
        hs = horses(h)
        print("─" * 96)
        print("%2dR %sm %s %s  %d頭" % (R, dist, ms.group(1) if ms else "",
                                        ms.group(2) if ms else "", len(hs)))
        for z in hs:
            mk, note = judge(z, track, dist) if dist else ("?", "距離が読めません")
            tot[mk] += 1
            if allmode or mk in ("◎", "?"):
                print("   %s %2d %-14s %s" % (mk, z["ub"], z["name"][:14], note))
        if not allmode and not [1 for z in hs
                                if dist and judge(z, track, dist)[0] in ("◎", "?")]:
            print("   該当なし")
        time.sleep(0.6)
    print("─" * 96)
    print("合計 ", "  ".join("%s%d頭" % (k, v) for k, v in tot.items()))


if __name__ == "__main__":
    main()
