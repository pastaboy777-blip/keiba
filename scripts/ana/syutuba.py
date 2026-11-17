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
           走破タイム t（秒）と、自前半 zen＝t−上がり3F

── ★ 当日に取り直すこと（CLAUDE.md ルール3）

  **馬体重と増減とオッズと人気は、前日は空で、当日に入る。**
  前日に作るカードは下見。**発走30分前に取り直して印を打ち直す**のが本来の形。
  この取得そのものは何度走らせても同じ形で返るので、当日そのまま上書きしてよい。

── ★ 通過順は楽天ならマスクされない（2026-10-24に確認）

  競馬ブックは cookie が切れると通過順もラップも **** になる。
  楽天は19日前のレースでも括弧つきの生の形で残っていた。
  ルール5「通過順は開催当日に取る」は競馬ブックの話で、楽天には当てはまらない。

── ★ 角が6段ある鞍でも c1／c4 はずれていない（2026-11-14 に実データで確認）

  川崎2000m・2100m・大井2400m は**向正面スタートで角を6つ通る**。
  結果ページのコーナー通過順位も6段で出る（`kekka.py` 冒頭と同じ話）。

    川崎2000m … ３角 ４角 １角 ２角 ３角 ４角
    大井2400m … １周３角 １周４角 １角 ２角 ２周３角 ２周４角  ← 札の形が違う

  **出馬表の過去走欄はこの6段のうち4つだけを出す。**
  出すのは**最初の2つと最後の2つ**で、真ん中の １角・２角 を落としている。

    川崎 10/14 12R（2000m・13頭）… 12頭ぜんぶ一致
      ③ビルドラポール  過去走欄 7-5-8-3    結果頁6段 7-5-6-6-8-3
      ⑫ジーカンピオーネ 過去走欄 1-5-3-10   結果頁6段 1-5-6-6-3-10
    大井 10/5 7R（2400m・12頭）… 9頭ぜんぶ一致
      ②ストライクノワール 過去走欄 3-5-4-3  結果頁6段 3-5-3-3-4-3

  つまり **`c1` = q[0] は最初に通った角、`c4` = q[-1] は最終4角**で、どちらも正しい。
  角が4段以下の鞍では過去走欄＝結果頁の全段（大井1400mは3値、大井1200mは2値）。

  ★ ずれているのは `harvest.py` の `corners()` のほう（札ごとに最初の一致を取るので、
    6段の鞍では「４角」に**1周目の4角**が入り最終4角が落ちる）。**こちらは別物。**
    隊列図（`tenkai_zu.py`）の pos／gain はこのファイルの c1／c4 から出ているので、
    harvest のずれは図には入らない。
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


#  ── 当日のオッズと人気（2026-11-16 に取りこぼしを直した）
#
#  楽天の書き方は2通りあって、**いまの大井は後者**。
#
#    旧 … 「22.5倍」「6番人気」
#    今 … `<span class="rate">` のセルに 「22.5 （6人気）」
#         **`倍` も `番人気` も付かない。括弧は全角。**
#         1番人気は `<span class="hot">`、最高オッズは `<span class="dark">` で
#         数字が包まれる（タグを落とせば同じ形になる）。
#
#  `倍`／`番人気` を待っていたので、11/16 の card.json が全頭 odds=null / nin=null
#  になっていた。**両方読む。**
RATE = re.compile(r'<(span|div)[^>]*class="rate"')
R_ODDS = re.compile(r"^\s*([\d,]+\.\d+|[\d,]+)")
R_NIN = re.compile(r"[（(]\s*(\d{1,2})\s*人気\s*[）)]")
O_BAI = re.compile(r"(\d+\.\d)\s*倍")
N_BAN = re.compile(r"(\d{1,2})\s*番人気")


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


def nosp(s):
    """名前から空白（全角スペースを含む）を落とす。
       楽天は1字姓を「所　蛍」と全角スペースで埋めてくる。jk_soto.json 側は素の3字。"""
    s = re.sub(r"\s+", "", s or "")
    return s or None


def profile(blk):
    """`class="profile"` のセルから（騎手, 調教師）を取る。

    セルの中身は <br> 区切りで
      性齢 ／ 毛色 ／ 負担重量 ／ 騎手 ／（所属）／【勝率】／【3着内率】／ 調教師。

    ★ 以前は平らにしたブロック全体を
      `(?:\\d+\\.\\d)\\s+([^\\s（）\\[\\]【】]{2,6})\\s*[（(]` で探していた。
      名前に全角スペースが入る騎手（1字姓の「所　蛍」など）はこの名前パターンに
      当たらないので先頭で照合できず、そのまま過去走の表まで走って
      「54.0 1:45.2 (1.6)」を拾い、**jk が `1:45.2` になっていた**
      （2026-10-27 大井10R ①ジュアルエリモ）。セルを <br> で区切って読めばずれない。
    """
    m = re.search(r'class="profile"[^>]*>(.*?)</td>', blk, re.S)
    if not m:
        return None, None
    ps = [x for x in (flat(y).strip() for y in re.split(r"<br\s*/?>", m.group(1))) if x]
    jk = tr = None
    for i, x in enumerate(ps[:-1]):
        if re.fullmatch(r"\d+(?:\.\d)?", x):          # 負担重量。その次が騎手
            nx = ps[i + 1]
            if not re.search(r"[【】（）()]", nx):     # 騎手が未定の鞍は（所属）が来る
                jk = nosp(nx)
            break
    if ps and not re.search(r"[【】（）()]", ps[-1]):  # 最後が調教師
        tr = nosp(ps[-1])
    return jk, tr


def inner(h, m):
    """開始タグ `m` の中身だけを返す（同じ名前の入れ子を数える）。

    `class="rate"` のセルは中に `<span class="hot">` が入ることがあるので、
    最初の `</span>` で切ると数字が途中で切れる。"""
    tag = m.group(1)
    j = h.find(">", m.end())
    if j < 0:
        return ""
    d, k = 1, j + 1
    for x in re.finditer(r"<(/?)%s\b" % tag, h[k:k + 4000]):
        d += -1 if x.group(1) else 1
        if d == 0:
            return h[k:k + x.start()]
    return h[k:k + 300]


def odds_nin(blk, fb):
    """（単勝オッズ, 人気）。**前日は欄が空なので (None, None)。**

    ★ 人気として拾ってよいのは出馬表の人気欄だけ（CLAUDE.md ルール34）。
      同じブロックには過去走の表が並んでいて、そこには
      そのときの人気「3人」・走破タイム「1:45.2」・馬体重「496k」・
      着差「(1.6)」・増減「(+4)」が入っている。
      だから**ブロック全体を数字で探しに行かない**。`class="rate"` のセルの中だけを見る。
      旧の書き方だけは `倍`／`番人気` という字が付いていて過去走欄には出ないので、
      そちらに限ってブロック全体から拾ってよい。
    """
    o = n = None
    m = RATE.search(blk)
    if m:
        s = flat(inner(blk, m)).strip()
        mo, mn = R_ODDS.match(s), R_NIN.search(s)
        if mo:
            try:
                o = float(mo.group(1).replace(",", ""))
            except ValueError:
                o = None
        if mn:
            n = int(mn.group(1))
    if o is None:                              # 旧「22.5倍」
        mo = O_BAI.search(fb)
        o = float(mo.group(1)) if mo else None
    if n is None:                              # 旧「6番人気」
        mn = N_BAN.search(fb)
        n = int(mn.group(1)) if mn else None
    return o, n


def secs(s):
    """走破タイム「1:41.2」「41.2」を秒に。★ 自前半＝走破タイム−上がり3F。
       楽天は前半タイムを出さないが、引き算で出る。"""
    m, _, r = s.rpartition(":")
    try:
        return round(int(m) * 60 + float(r), 1) if m else float(r)
    except ValueError:
        return None


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
            sec, agf = secs(tm), float(ag)
            runs.append({"chaku": int(ch), "baba": baba, "n": int(n), "venue": ven,
                         "date": dt, "dist": int(dist), "sur": sur, "nk": int(nk),
                         "kin": float(kin), "sa": float(sa), "agari": agf,
                         "t": sec, "zen": round(sec - agf, 1) if sec else None,
                         "w": int(w), "waku": int(wk), "tsuka": q,
                         "c1": q[0] if q else None, "c4": q[-1] if q else None})
        # ★ 騎手と調教師（2026-11-11 に追加 / 2026-11-14 に profile セル読みへ直した）
        #   オッズ頁（tanfuku）は発走の数時間前まで開かないので、前夜はここからしか取れない。
        #   騎手は内外（jk_soto.json）に、調教師は2頭出しの判定に使う。
        #   減量記号（△▲◇☆★◎）は付いたまま返す（照合側で外す ── CLAUDE.md ルール21★）。
        mjk, mtr = profile(blk)
        # ★ 当日だけ入る欄。前日は空
        od, nk = odds_nin(blk, fb)
        mww = re.search(r"\s(\d{3})k?\s*[（(]\s*([-+±]?\d+)\s*[）)]", fb)
        hs.append({"ub": int(mu.group(1)), "waku": int(mw[-1]) if mw else None,
                   "name": mn.group(1).strip(), "past": runs,
                   "odds": od, "nin": nk,
                   "w": int(mww.group(1)) if mww else None,
                   "dw": mww.group(2).replace("±", "+") if mww else None,
                   "jk": mjk, "tr": mtr})
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
