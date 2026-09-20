#!/usr/bin/env python3
"""**今週の中央（JRA）で馬券になった馬を、前走からの間隔で仕分ける。**

    python3 scripts/jra_week.py --dates 20260919,20260920
    python3 scripts/jra_week.py --dates 20260919 --place 中山

netkeiba の公開ページだけで動く（Cookie 不要）。

── 何を確かめる道具か ──────────────────────────────

**硬直（激走の反動）に時定数はあるか。**

Mの法則は「激走の後に反動が来る」とだけ言い、**いつまで続くか**を言わない。
ユーザーがモリノセピアの馬柱で7週という形を見つけた（2026-09-20）:

    2026-04-12 福島 9人気3着（激走）→ **10.9週** → 06-27 福島 7人気3着  好走
    2026-06-27 福島 7人気3着（激走）→  **4.1週** → 07-26 新潟 4人気7着  凡走

これを今週の中央で当てる。`src/nankeiba/core/mhousoku.py` の `STIFF_WEEKS`
（＝7.0週）が、この道具で測る対象そのもの。

⚠️⚠️ **「馬券になった馬」だけを見てはいけない。**分母が無いと何も言えない。
   3着内率は全体で約 3/頭数 になるので、**帯ごとの3着内率を全出走馬で
   比べる**こと。この道具は全出走馬を取ってから馬券圏内を数える。

⚠️⚠️ **「磁場」という言葉は使わない。**（ユーザー指定 2026-09-20）
   測れているのは「**前走と同じ競馬場か**」だけなので、そう書く。経度差2度の
   抽象を被せても何も足さない。今週の中央618頭で実測:

       経度2度超 動いた   32/134 = 23.9%   ／  2度以内  85/362 = 23.5%   ← +0.4pt
       7週以上あけた     61/234 = 26.1%   ／  7週未満  56/262 = 21.4%   ← **+4.7pt**

⚠️⚠️ **「競馬場が替わった」は変数になっていない。**JRAの開催ローテーションの
   結果、7週以上あけた馬はほぼ全部が別の競馬場から来る（実測：中山 118頭中
   **110頭(93%)**、阪神 116頭中 **97頭(84%)**）。ほぼ定数なので差が出ない。
   さらに競馬場ごとに割ると向きが**逆になる**（中山 +14.8pt ／ 阪神 −6.9pt）。
   **混ぜたままなら開催カレンダーの形を見ているだけ。**

⚠️ **恒久ルール5に触れないこと。**見るのは**今週の開催**だけ。過去開催を
   まとめた回収率・勝率の集計はしない。`--dates` に今週以外を渡さない。

── データ源 ────────────────────────────────────

    レース一覧  race.netkeiba.com/top/race_list_sub.html?kaisai_date=YYYYMMDD
    馬柱       race.netkeiba.com/race/shutuba_past.html?race_id=...
    結果       race.netkeiba.com/race/result.html?race_id=...

⚠️ **馬柱ページ（shutuba_past）は1ページで全馬の過去走が取れる。**馬ごとの
   成績ページ（db.netkeiba.com/horse/{id}/）は**成績表を返さなくなっている**
   （2026-09 時点。プロフィール表だけが入っている）。馬単位で取りに行くと
   1レース24頭×48レース＝1000ページ超になる上、そもそも取れない。

⚠️ 馬柱の過去走セルに**着順は文字として入っていない**。`<td class="Past
   Ranking_N">` の **N が着順**で、**1〜3着にしか付かない**。つまり
   「クラスが付いている＝馬券圏内」。激走の判定にはこれで足りる。

⚠️ 節度を持って取得すること（`SLEEP` 秒あけ、キャッシュする）。
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.core import mhousoku as M                   # noqa: E402

CACHE = "data/cache/netkeiba"
#: 開催ごとの記録。**前向きに積むための置き場**（恒久ルール4）。
LOG_DIR = "data/jra_week"
SLEEP = 1.0
UA = "Mozilla/5.0 (compatible; keiba-research/1.0)"
#: 「激走」＝この人気以下で3着内。mhousoku と揃える。
GEKISO_POP = M.GEKISO_POP
#: 硬直が抜ける週数。mhousoku と揃える。
STIFF_WEEKS = M.STIFF_WEEKS
#: JRA 場コード。
JYO = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
       "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}


def get(url: str, key: str) -> str:
    """取得してキャッシュする。**同じページを二度取りに行かない。**"""
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, re.sub(r"[^0-9A-Za-z]+", "_", key).strip("_") + ".html")
    if os.path.exists(p):
        return open(p, encoding="utf-8", errors="replace").read()
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Referer": "https://race.netkeiba.com/"})
    raw = urllib.request.urlopen(req, timeout=30).read()
    try:
        t = raw.decode("utf-8")
    except UnicodeDecodeError:
        t = raw.decode("euc_jp", errors="replace")
    open(p, "w", encoding="utf-8").write(t)
    time.sleep(SLEEP)
    return t


def _txt(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", s)).split())


def race_ids(date: str) -> list[str]:
    h = get(f"https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={date}",
            f"racelist_{date}")
    return sorted(set(re.findall(r"race_id=(\d{12})", h)))


def parse_past(h: str) -> dict:
    """馬柱ページ → {馬番: {name, weight_diff, runs:[{date,place,pop,inmoney}]}}

    ⚠️ 着順は `Ranking_N` クラスにしか無く、**1〜3着にしか付かない**。
    """
    out: dict = {}
    for row in re.findall(r'<tr[^>]*class="[^"]*HorseList.*?</tr>', h, re.S):
        um = re.search(r'<td[^>]*class="Waku[^"]*"[^>]*>.*?</td>\s*'
                       r'<td[^>]*>\s*(\d+)\s*</td>', row, re.S)
        nm = re.search(r'/horse/\d+/?"[^>]*>\s*([^<]{2,24}?)\s*<', row, re.S)
        if not (um and nm):
            continue
        info = re.search(r'class="Horse_Info".*?</td>', row, re.S)
        wd = re.search(r"(\d{3})kg\s*\(([-+]?\d+)\)", _txt(info.group(0)) if info else "")
        runs = []
        for cls, cell in re.findall(r'<td[^>]*class="(Past[^"]*)"[^>]*>(.*?)</td>',
                                    row, re.S):
            d = re.search(r"<span>([\d.]+)&nbsp;(\S+?)</span>", cell)
            if not d:
                continue
            pop = re.search(r"(\d+)頭.*?(\d+)人", _txt(cell))
            rk = re.search(r"Ranking_(\d+)", cls)
            runs.append({"date": d.group(1).replace(".", "-"), "place": d.group(2),
                         "field": int(pop.group(1)) if pop else None,
                         "pop": int(pop.group(2)) if pop else None,
                         "finish": int(rk.group(1)) if rk else None})
        out[int(um.group(1))] = {"name": nm.group(1), "runs": runs,
                                 "wdiff": int(wd.group(2)) if wd else None}
    return out


def parse_result(h: str) -> dict:
    """結果ページ → {馬番: {finish, name, pop}}"""
    out: dict = {}
    for row in re.findall(r'<tr[^>]*class="[^"]*HorseList.*?</tr>', h, re.S):
        c = [_txt(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(c) < 11 or not c[0].isdigit() or not c[2].isdigit():
            continue
        out[int(c[2])] = {"finish": int(c[0]), "name": c[3],
                          "pop": int(c[9]) if c[9].isdigit() else None}
    return out


def weeks_between(a: str, b: str) -> float | None:
    """'2026-06-27' と '20260919' の週数。"""
    import datetime as dt
    try:
        d1 = dt.date(*map(int, a.split("-")))
        d2 = dt.date(int(b[:4]), int(b[4:6]), int(b[6:]))
        return (d2 - d1).days / 7.0
    except (ValueError, TypeError):
        return None


def classify(runs: list, date: str) -> tuple[str, float | None, dict | None]:
    """前走が激走か、そこから何週かで帯に分ける。

    返す帯:
        "激走→7週以内"   前走が人気薄で3着内、かつ詰めて使った＝**反動が出る側**
        "激走→7週超"     反動は抜けた側
        "前走ふつう"      激走していない
        "判定不能"        前走が読めない
    """
    if not runs:
        return "判定不能", None, None
    last = runs[0]
    w = weeks_between(last["date"], date)
    if w is None:
        return "判定不能", None, last
    gek = bool(last.get("finish") and last["finish"] <= 3
               and last.get("pop") and last["pop"] >= GEKISO_POP)
    if not gek:
        return "前走ふつう", w, last
    return ("激走→7週以内" if w <= STIFF_WEEKS else "激走→7週超"), w, last


#: 人気帯。**ここで割らないと市場が織り込んだものを「発見」してしまう。**
POP_BANDS = (("1〜3人気", 1, 3), ("4〜5人気", 4, 5),
             ("6〜9人気", 6, 9), ("10人気以下", 10, 99))


def by_pop(a: list, b: list, la: str, lb: str) -> None:
    """2群を人気帯ごとに比べる。**これがこの道具でいちばん大事な関数。**

    ⚠️⚠️ **全体の率だけで判断してはいけない。**2026-09-20 の実測で、
       「その競馬場で3着内の好走歴がある」は全体で **+9.1pt (+1.93SE)** と
       いちばん強く見えたが、人気帯で割ると:

           1〜3人気 −3.1pt ／ 4〜5人気 −2.9pt ／ 6〜9人気 −1.8pt ／ 10人気以下 −6.1pt

       **4帯すべてマイナス。**+9.1pt は「好走歴のある馬が人気帯に偏っている」
       だけの見かけだった（シンプソンのパラドックス）。コース実績は市場が
       織り込み済みで、むしろ買われすぎ。

       同じ検査を「前走3着内 × 7週以上」に掛けると4帯すべてプラスで残った。
       **全体の差ではなく、帯ごとに同じ向きが出るかで判断すること。**
    """
    import math
    print(f"  {'人気帯':<12}{la:>18}{lb:>18}{'差':>9}{'SE':>8}")
    for lab, lo, hi in POP_BANDS:
        A = [r for r in a if r["pop"] and lo <= r["pop"] <= hi]
        B = [r for r in b if r["pop"] and lo <= r["pop"] <= hi]
        if not A or not B:
            print(f"  {lab:<12}{cellp(A):>18}{cellp(B):>18}{'—':>9}{'—':>8}")
            continue
        x, y = sum(1 for r in A if r["finish"] <= 3), sum(1 for r in B if r["finish"] <= 3)
        p1, p2 = x / len(A), y / len(B)
        se = math.sqrt(p1 * (1 - p1) / len(A) + p2 * (1 - p2) / len(B))
        z = (p1 - p2) / se if se else 0.0
        print(f"  {lab:<12}{cellp(A):>18}{cellp(B):>18}"
              f"{(p1-p2)*100:>+8.1f}pt{z:>+7.2f}")


def cellp(g: list) -> str:
    if not g:
        return "n=0"
    im = sum(1 for r in g if r["finish"] <= 3)
    return f"{im/len(g)*100:>5.1f}% ({im}/{len(g)})"


def cell(g: list) -> str:
    """1マス分：出走／3着内／率／1着／人気薄(6人気以下)の3着内。"""
    if not g:
        return f"{0:>6}{'—':>7}{'—':>8}{'—':>6}{'—':>18}"
    im = [r for r in g if r["finish"] <= 3]
    w1 = [r for r in g if r["finish"] == 1]
    ana = [r for r in g if r["pop"] and r["pop"] >= 6]
    anam = [r for r in ana if r["finish"] <= 3]
    a = f"{len(anam)}/{len(ana)}" + (f" ({len(anam)/len(ana)*100:.0f}%)" if ana else "")
    return (f"{len(g):>6}{len(im):>7}{len(im)/len(g)*100:>7.1f}%"
            f"{len(w1):>6}{a:>18}")


def main() -> None:
    ap = argparse.ArgumentParser(description="今週の中央を間隔で仕分ける")
    ap.add_argument("--dates", help="YYYYMMDD,YYYYMMDD")
    ap.add_argument("--place", help="場を絞る（中山 など）")
    ap.add_argument("--pool", action="store_true",
                    help="**これまでに記録した開催を全部まとめて読む**")
    args = ap.parse_args()
    if not (args.dates or args.pool):
        ap.error("--dates か --pool のどちらかが要る")

    # ⚠️ **--pool は過去開催の一括検証ではない。**恒久ルール5が禁じているのは
    #    「n万頭で測ったら効かなかった」を持ち出すこと。ここで読むのは
    #    **自分が毎週その場で記録してきた開催だけ**で、ルール4（正直な記録）の側。
    #    1開催では 0.87SE にしかならないので、**前向きに積む以外に道が無い**。
    if args.pool:
        import glob
        import json
        rows = []
        for f in sorted(glob.glob(os.path.join(LOG_DIR, "*.jsonl"))):
            rows += [json.loads(x) for x in open(f, encoding="utf-8") if x.strip()]
        if args.place:
            rows = [r for r in rows if r["place"] == args.place]
        print(f"  記録済みの開催を {len(glob.glob(os.path.join(LOG_DIR,'*.jsonl')))}"
              f"ファイル読みました（{len(rows)}頭）", file=sys.stderr)
        report(rows)
        return

    rows: list = []
    for date in args.dates.split(","):
        for rid in race_ids(date):
            place = JYO.get(rid[4:6], rid[4:6])
            if args.place and place != args.place:
                continue
            rno = int(rid[10:12])
            try:
                past = parse_past(get(
                    f"https://race.netkeiba.com/race/shutuba_past.html?race_id={rid}",
                    f"past_{rid}"))
                res = parse_result(get(
                    f"https://race.netkeiba.com/race/result.html?race_id={rid}",
                    f"res_{rid}"))
            except Exception as e:                          # noqa: BLE001
                print(f"  {date} {place}{rno}R × {e}", file=sys.stderr)
                continue
            if not res:
                print(f"  {date} {place}{rno}R × 結果がまだ出ていない", file=sys.stderr)
                continue
            for um, r in res.items():
                p = past.get(um) or {}
                band, w, last = classify(p.get("runs") or [], date)
                # ⚠️ **その競馬場で過去に3着内に走ったことがあるか**（コース実績）。
                #    全体では最も強く見えるが、人気帯で割ると4帯とも消える。
                #    `by_pop()` の docstring を読むこと。比較用に必ず持つ。
                rows.append({"date": date, "place": place, "rno": rno, "um": um,
                             "name": r["name"], "finish": r["finish"],
                             "pop": r["pop"], "band": band, "weeks": w,
                             "last": last, "wdiff": p.get("wdiff"),
                             "course_good": any(
                                 x["place"] == place and x["finish"]
                                 for x in (p.get("runs") or []))})
            print(f"  {date} {place}{rno:>2}R ○ {len(res)}頭", file=sys.stderr, flush=True)

    if not rows:
        print("取れませんでした", file=sys.stderr)
        return

    # ⚠️ **その場で記録する。**1開催では 0.87SE にしかならないので、
    #    前向きに積む以外に道が無い。--pool でまとめて読む。
    import json
    os.makedirs(LOG_DIR, exist_ok=True)
    lp = os.path.join(LOG_DIR, args.dates.replace(",", "_") + ".jsonl")
    with open(lp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  記録 → {lp}（{len(rows)}頭）", file=sys.stderr)
    report(rows)


def report(rows: list) -> None:
    """集計と表示。--pool でも同じものを通す。"""
    dates = ",".join(sorted({r["date"] for r in rows}))
    n_race = len({(r["date"], r["place"], r["rno"]) for r in rows})
    inmoney = [r for r in rows if r["finish"] <= 3]
    print(f"\n{'='*92}\n 中央　{dates}　{n_race}レース／{len(rows)}頭"
          f"　馬券になった馬 {len(inmoney)}頭\n{'='*92}")

    # ── ① 馬券になった馬を、前走からの間隔で仕分ける ──
    print("\n■ 馬券圏内の馬　前走からの間隔")
    for b in ("激走→7週以内", "激走→7週超", "前走ふつう", "判定不能"):
        g = [r for r in inmoney if r["band"] == b]
        if not g:
            continue
        ws = [r["weeks"] for r in g if r["weeks"] is not None]
        med = f"　中央値{sorted(ws)[len(ws)//2]:.1f}週" if ws else ""
        print(f"  {b:<12} {len(g):>3}頭（{len(g)/len(inmoney)*100:>4.1f}%）{med}")

    # ── ② ⚠️ 分母つきで比べる。ここが本体 ──
    print("\n■ **帯ごとの3着内率**（分母＝全出走馬。ここを見ないと何も言えない）")
    print(f"  {'帯':<14}{'出走':>6}{'3着内':>7}{'率':>8}{'1着':>6}"
          f"{'人気薄(6人気以下)の3着内':>26}")
    base = len(inmoney) / len(rows) * 100
    for b in ("激走→7週以内", "激走→7週超", "前走ふつう", "判定不能"):
        g = [r for r in rows if r["band"] == b]
        if not g:
            continue
        im = [r for r in g if r["finish"] <= 3]
        w1 = [r for r in g if r["finish"] == 1]
        ana = [r for r in g if r["pop"] and r["pop"] >= 6]
        anam = [r for r in ana if r["finish"] <= 3]
        print(f"  {b:<14}{len(g):>6}{len(im):>7}{len(im)/len(g)*100:>7.1f}%"
              f"{len(w1):>6}{f'{len(anam)}/{len(ana)}':>16}"
              f"{f'({len(anam)/len(ana)*100:.1f}%)' if ana else '':>10}")
    print(f"  {'全体':<14}{len(rows):>6}{len(inmoney):>7}{base:>7.1f}%"
          f"{len([r for r in rows if r['finish']==1]):>6}")

    # ── ③ 間隔 × 競馬場が変わったか ─────────────────────────
    #    ⚠️⚠️ **「磁場」という言葉は使わない。**（ユーザー指定 2026-09-20）
    #       中島理論の磁場は「どこで暮らしたか」で、経度差2度を閾値にする。
    #       だが今週の中央618頭で測ると、**経度は何も足していなかった**:
    #
    #           経度2度超 動いた   32/134 = 23.9%
    #           2度以内          85/362 = 23.5%   ← 差 +0.4pt。ゼロ
    #           （7週以上あけた   61/234 = 26.1% vs 7週未満 21.4%。**こちらは効く**）
    #
    #       そもそも前走と今走の競馬場が離れていても、それは**遠征**であって
    #       引っ越しではない（中島の時定数は7週、遠征は数日）。放牧先はどの
    #       データにも載っていない。**測れているのは「競馬場が変わったか」だけ**
    #       なので、そう書く。経度の抽象化を被せない。
    same = [r for r in rows if r["last"] and r["last"]["place"] == r["place"]]
    diff = [r for r in rows if r["last"] and r["last"]["place"] != r["place"]]
    print("\n■ **間隔 × 前走と同じ競馬場か**")
    print(f"  {'':<26}{'出走':>6}{'3着内':>7}{'率':>8}{'1着':>6}"
          f"{'人気薄(6人気以下)':>18}")
    for label, pool in (("前走と同じ競馬場", same), ("別の競馬場", diff)):
        for wlab, sel in ((f"{STIFF_WEEKS:.0f}週以上あけた",
                           lambda r: r["weeks"] is not None and r["weeks"] >= STIFF_WEEKS),
                          (f"{STIFF_WEEKS:.0f}週未満",
                           lambda r: r["weeks"] is not None and r["weeks"] < STIFF_WEEKS)):
            g = [r for r in pool if sel(r)]
            print(f"  {label:<14}×{wlab:<11}{cell(g)}")
    print(f"  {'全体':<26}{cell(rows)}")

    hit = [r for r in diff if r["finish"] <= 3 and r["weeks"] is not None
           and r["weeks"] >= STIFF_WEEKS]
    if hit:
        print(f"\n■ **{STIFF_WEEKS:.0f}週以上あけて、競馬場も替わって、馬券になった馬** "
              f"{len(hit)}頭")
        for r in sorted(hit, key=lambda x: x["pop"] or 99, reverse=True):
            L = r["last"]
            print(f"  {r['date'][4:6]}/{r['date'][6:]} {r['place']}{r['rno']:>2}R "
                  f"{r['name']:<13}{r['finish']}着"
                  f"{(str(r['pop'])+'人気') if r['pop'] else '':>7}"
                  f"　前走 {L['date']} {L['place']} "
                  f"{L['pop']}人気{(str(L['finish'])+'着') if L['finish'] else '着外'}"
                  f"　→ {r['weeks']:.1f}週")

    # ── ③' **前走で好走したか × 間隔。** ───────────────────
    #    ユーザーの読み（2026-09-20）:「好走して競馬場の影響を7週受けると好走した」
    #
    #    ⚠️ ③の「激走」は**人気薄(5人気以下)で3着内**に絞っていたので n=25/16
    #       しか無かった。ここは**人気を問わず3着内**に広げる。こちらが本題。
    #
    #    ⚠️ 馬柱の着順は Ranking_N クラスにしか無く1〜3着にしか付かないので、
    #       `finish is None` ＝ 4着以下。**ちょうど「3着内か否か」で割れる。**
    def good(r) -> bool | None:
        return None if not r["last"] else (r["last"]["finish"] is not None)

    def longrest(r) -> bool | None:
        return None if r["weeks"] is None else (r["weeks"] >= STIFF_WEEKS)

    print("\n■ **前走で3着内だったか × 間隔**（「好走して7週あけると好走」）")
    print(f"  {'':<26}{'出走':>6}{'3着内':>7}{'率':>8}{'1着':>6}"
          f"{'人気薄(6人気以下)':>18}")
    for glab, gv in (("前走3着内", True), ("前走は着外", False)):
        for wlab, wv in ((f"{STIFF_WEEKS:.0f}週以上あけた", True),
                         (f"{STIFF_WEEKS:.0f}週未満", False)):
            g = [r for r in rows if good(r) is gv and longrest(r) is wv]
            print(f"  {glab:<14}×{wlab:<11}{cell(g)}")
    print(f"  {'全体':<26}{cell(rows)}")
    for pl in sorted({r["place"] for r in rows}):
        print(f"  ── {pl} だけ ──")
        for glab, gv in (("前走3着内", True), ("前走は着外", False)):
            for wlab, wv in ((f"{STIFF_WEEKS:.0f}週以上", True),
                             (f"{STIFF_WEEKS:.0f}週未満", False)):
                g = [r for r in rows if r["place"] == pl
                     and good(r) is gv and longrest(r) is wv]
                print(f"  {glab:<14}×{wlab:<11}{cell(g)}")

    # ── ③'' **人気帯で割る。ここが判定の本体。** ──────────────
    print(f"\n■ **前走3着内の馬を人気帯で割る**"
          f"（全体の差ではなく、**帯ごとに同じ向きが出るか**で判断する）")
    by_pop([r for r in rows if good(r) and longrest(r)],
           [r for r in rows if good(r) and longrest(r) is False],
           f"{STIFF_WEEKS:.0f}週以上あけた", f"{STIFF_WEEKS:.0f}週未満")
    print("\n  ⚠️ 比較用：**その競馬場での好走歴**（全体では最も強く見えるが…）")
    by_pop([r for r in rows if r["course_good"]],
           [r for r in rows if not r["course_good"]],
           "その場で好走歴あり", "好走歴なし")

    # ── ④ **競馬場ごとに割る。** ─────────────────────────
    #    ⚠️⚠️ **競馬場を混ぜたまま読んではいけない。**この週の「7週以上あけて
    #       競馬場も替わった」馬はほとんどが阪神で、前走は小倉・札幌・函館に偏る。
    #       **小倉/札幌/函館は7月で終わる夏開催**なので、「夏に走って秋に阪神へ
    #       戻る」馬は自動的に (a) 間隔が空き (b) 競馬場が替わる。
    #       つまり混ぜたままの数字は**開催カレンダーの形**を見ている疑いが強い。
    #       競馬場ごとに割って、同じ向きが出るかを必ず確かめること。
    print("\n■ **競馬場ごと**（混ぜたままだと開催カレンダーの形を見てしまう）")
    for pl in sorted({r["place"] for r in rows}):
        pr = [r for r in rows if r["place"] == pl]
        print(f"\n  ── {pl}　{len({(r['date'], r['rno']) for r in pr})}レース"
              f"／{len(pr)}頭 ──")
        print(f"  {'':<26}{'出走':>6}{'3着内':>7}{'率':>8}{'1着':>6}"
              f"{'人気薄(6人気以下)':>18}")
        for lab, sel in ((f"{STIFF_WEEKS:.0f}週以上あけた",
                          lambda r: r["weeks"] is not None and r["weeks"] >= STIFF_WEEKS),
                         (f"{STIFF_WEEKS:.0f}週未満",
                          lambda r: r["weeks"] is not None and r["weeks"] < STIFF_WEEKS)):
            g = [r for r in pr if sel(r)]
            print(f"  {lab:<26}{cell(g)}")
        for lab, ok in (("うち競馬場が替わった", False), ("うち前走と同じ競馬場", True)):
            g = [r for r in pr if r["last"] and r["weeks"] is not None
                 and r["weeks"] >= STIFF_WEEKS
                 and (r["last"]["place"] == pl) is ok]
            print(f"  {STIFF_WEEKS:.0f}週以上 {lab:<19}{cell(g)}")
        print(f"  {'この場の全体':<26}{cell(pr)}")
        src = {}
        for r in pr:
            if r["last"] and r["weeks"] is not None and r["weeks"] >= STIFF_WEEKS:
                src[r["last"]["place"]] = src.get(r["last"]["place"], 0) + 1
        if src:
            print(f"  {STIFF_WEEKS:.0f}週以上あけた馬の前走の場: "
                  + "、".join(f"{k}{v}" for k, v in
                              sorted(src.items(), key=lambda x: -x[1])))

    # ── ⑤ 「激走→7週以内」に入りながら馬券になった馬（理論が外した馬）──
    ng = [r for r in inmoney if r["band"] == "激走→7週以内"]
    if ng:
        print(f"\n■ **理論が外した馬**（反動が出るはずが馬券になった）{len(ng)}頭")
        for r in sorted(ng, key=lambda x: x["weeks"] or 9):
            L = r["last"]
            print(f"  {r['date'][4:6]}/{r['date'][6:]} {r['place']}{r['rno']:>2}R "
                  f"{r['name']:<12}{r['finish']}着"
                  f"{(str(r['pop'])+'人気') if r['pop'] else '':>6}"
                  f"　前走 {L['date']} {L['place']} {L['pop']}人気{L['finish']}着"
                  f"　→ {r['weeks']:.1f}週")

    print(f"\n{'─'*92}")
    print("⚠️ **今週の開催だけを見ている**（恒久ルール5）。過去開催の一括検証はしない。\n"
          "⚠️ 7週という値は中島理論から借りたもので、**まだ測っていない**。"
          "この出力は値を決めるためのものではなく、\n   今週それが効いていたかを"
          "正直に記録するためのもの。", file=sys.stderr)


if __name__ == "__main__":
    main()
