#!/usr/bin/env python3
"""jra_ana の予想ログを実結果と突き合わせる。

    python3 scripts/jra_verify.py --log out/jra_ana_log.csv --date 20260801

⚠️ 「当たった/外れた」を盛らないための決まりごと:

  * **必ず母数を並べる。** 候補は全部「6番人気以下」に絞ってあるので、
    素の勝率を出しても意味がない。同じ日の**6番人気以下の全馬**を
    ベースラインとして必ず一緒に出す。それを上回っていなければ、
    この式は何もしていない。
  * 候補が出たレースだけを見ない。**候補ゼロのレースも分母に入れる。**
  * サンプルが小さいときは、率よりも実数（何頭中何頭）を先に読むこと。
    36レースは「傾向が見えた」と言える大きさではない。
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nankeiba.scraping import keibabook as kb          # noqa: E402

#: ログの列数 → 版。追記していくと古い版の行が混ざるので、幅で見分ける。
SCHEMAS = {
    18: ["日付", "場", "R", "馬場種", "距離", "馬番", "馬名", "印", "条件指数",
         "条件順", "実力指数", "実力順", "市場人気", "市場ソース", "人気薄好走",
         "スコア", "残差SD", "着順"],
    21: ["日付", "場", "R", "馬場種", "距離", "馬番", "馬名", "印", "条件指数",
         "条件順", "条件走数", "ピーク何走前", "実力指数", "実力順",
         "市場人気", "市場ソース", "人気薄好走", "スコア", "残差SD", "判別可否", "着順"],
    22: ["日付", "場", "R", "馬場種", "距離", "馬番", "馬名", "印", "条件指数",
         "条件順", "ノイズ耐性", "条件走数", "ピーク何走前", "実力指数", "実力順",
         "市場人気", "市場ソース", "人気薄好走", "スコア", "残差SD", "判別可否", "着順"],
}


def read_log(path: str, date: str | None, *, latest_only: bool = True):
    """⚠️ ログは追記なので**古い版の行が混ざる**。列数で版を見分ける。

    版によって候補そのものが変わるので、混ぜて集計すると
    「どの版の成績なのか」が分からなくなる。既定では**その日のいちばん新しい
    版の行だけ**を残す。
    """
    raw = []
    with open(path, encoding="utf-8-sig") as fh:
        for c in csv.reader(fh):
            if not c or c[0].startswith("日付"):
                continue
            cols = SCHEMAS.get(len(c))
            if not cols:
                continue
            r = dict(zip(cols, c))
            if date and r["日付"].replace("-", "") != date:
                continue
            raw.append((len(c), r))
    if not raw:
        return []
    if latest_only:
        newest = max(n for n, _ in raw)
        raw = [(n, r) for n, r in raw if n == newest]
        print(f"（ログは{newest}列版の行だけを使う。古い版の行は無視）", file=sys.stderr)
    return [r for _, r in raw]


def pct(a, b):
    return f"{a}/{b} = {a / b:.0%}" if b else f"{a}/{b} = -"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="out/jra_ana_log.csv")
    ap.add_argument("--date", required=True)
    ap.add_argument("--cookie", default="data/.keibabook_cookie")
    ap.add_argument("--out", help="着順を埋めたCSVの書き出し先")
    ap.add_argument("--all-versions", action="store_true",
                    help="古い版の行も混ぜる（既定は最新版のみ）")
    args = ap.parse_args()

    rows = read_log(args.log, args.date, latest_only=not args.all_versions)
    if not rows:
        print("そのログに該当日の行が無い。", file=sys.stderr)
        sys.exit(1)
    # 同じ(場,R,馬番)が複数版で重複するので、いちばん新しい版を残す
    uniq = {}
    for r in rows:
        uniq[(r["場"], r["R"], r["馬番"])] = r
    rows = list(uniq.values())

    client = kb.KeibabookClient.from_cookie_file(args.cookie)
    places = sorted({r["場"] for r in rows})
    ids = {p: kb.find_meeting_cyuou(client, args.date, p) for p in places}

    # --- 実結果 -------------------------------------------------------------
    fin, pops, done = {}, {}, set()
    for p in places:
        for rno in range(1, 13):
            try:
                res = kb.parse_result_cyuou(
                    client.get(f"/cyuou/seiseki/{ids[p][rno - 1]}", use_cache=False))
            except Exception:                          # noqa: BLE001
                continue
            if not res:
                continue
            done.add((p, str(rno)))
            for x in res:
                fin[(p, str(rno), x["name"])] = x["finish"]
                pops[(p, str(rno), x["name"])] = x.get("popularity")

    for r in rows:
        r["着順"] = fin.get((r["場"], r["R"], r["馬名"]))
        r["確定人気"] = pops.get((r["場"], r["R"], r["馬名"]))

    live = [r for r in rows if r["着順"]]
    未 = [r for r in rows if not r["着順"] and (r["場"], r["R"]) not in done]
    print(f"=== {args.date} jra_ana 検証 ===")
    print(f"候補 {len(rows)}頭 / 結果照合できた {len(live)}頭"
          + (f" / 未確定 {len(未)}頭" if 未 else "")
          + f" / 確定レース {len(done)}R\n")

    # --- ベースライン: その日の6番人気以下の全馬 -----------------------------
    base_n = base_w = base_3 = 0
    for (p, rno, _nm), pop in pops.items():
        if (p, rno) not in done or not pop or pop < 6:
            continue
        base_n += 1
        f = fin[(p, rno, _nm)]
        base_w += f == 1
        base_3 += f <= 3
    print("■ ベースライン（同じ日の6番人気以下・全馬）")
    print(f"  勝率   {pct(base_w, base_n)}")
    print(f"  複勝率 {pct(base_3, base_n)}\n")

    def block(title, sel):
        n = len(sel)
        if not n:
            print(f"■ {title}  該当なし\n")
            return
        w = sum(1 for r in sel if int(r["着順"]) == 1)
        t3 = sum(1 for r in sel if int(r["着順"]) <= 3)
        bw = base_w / base_n if base_n else 0
        b3 = base_3 / base_n if base_n else 0
        print(f"■ {title}")
        print(f"  勝率   {pct(w, n)}"
              + (f"   （ベース比 {(w / n) / bw:.2f}倍）" if bw else ""))
        print(f"  複勝率 {pct(t3, n)}"
              + (f"   （ベース比 {(t3 / n) / b3:.2f}倍）" if b3 else ""))
        print()

    block("候補ぜんぶ", live)
    block("◎（レース内スコア1位）だけ", [r for r in live if r["印"] == "◎"])

    st = [r for r in live if r.get("ノイズ耐性")]
    if st:
        for lo, hi, nm in ((0.75, 1.01, "耐性75%以上"), (0.6, 0.75, "耐性60〜75%"),
                           (0.0, 0.6, "耐性60%未満")):
            block(nm, [r for r in st if lo <= float(r["ノイズ耐性"]) < hi])
        block("ピークが3走以上前（市場が忘れている）",
              [r for r in st if r.get("ピーク何走前")
               and r["ピーク何走前"].isdigit() and int(r["ピーク何走前"]) >= 3])
        block("判別可（条件の幅が残差SDを超えたレース）",
              [r for r in st if r.get("判別可否") == "判別可"])

    print("■ 個別（条件指数の高い順）")
    print(f"  {'場R':<8}{'馬':<12}{'条件':>6}{'耐性':>6}{'人気':>5}{'着':>4}")
    for r in sorted(live, key=lambda r: -float(r["条件指数"]))[:40]:
        stv = f"{float(r['ノイズ耐性']):.0%}" if r.get("ノイズ耐性") else "-"
        f = int(r["着順"])
        mark = "🎯" if f == 1 else ("○" if f <= 3 else "")
        print(f"  {r['場'] + r['R'] + 'R':<8}{r['馬名'][:10]:<12}"
              f"{float(r['条件指数']):>6.2f}{stv:>6}"
              f"{r.get('確定人気') or r['市場人気']:>5}{f:>4} {mark}")

    if args.out:
        cols = SCHEMAS[22] + ["確定人気"]
        with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"\n→ {args.out}")


if __name__ == "__main__":
    main()
