#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""競馬ブック地方 調教の日次コレクター（1年分を無理なく貯める）。

会員Cookie(KEIBABOOK_COOKIE)必須。1レース=1フェッチで全馬の調教が取れる。
polite間隔・場フィルタ・レジューム(日ファイル単位)・Cookie失効検出つき。

使い方:
  export KEIBABOOK_COOKIE="PHPSESSID=...; ..."
  # 動作確認(1日・南関のみ・最大3R)
  python3 scripts/collect_keibabook_chokyo.py --from 20260710 --to 20260710 \
      --places 川崎 浦和 船橋 大井 --max-races 3
  # バックフィル(期間指定・南関のみ)
  python3 scripts/collect_keibabook_chokyo.py --from 20250701 --to 20260630 --places 川崎 浦和 船橋 大井

出力: data/samples/keibabook_chokyo_YYYYMMDD.jsonl（1行=1レース）。
注意: 有料サイトへの大量取得はToS配慮。間隔は詰めすぎない（既定1.8s）。失効したらCookie取り直し。
"""
from __future__ import annotations
import argparse, json, os, sys, time
from datetime import date, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import keibabook_chokyo as kb  # noqa: E402


def daterange(a: str, b: str):
    d0 = date(int(a[:4]), int(a[4:6]), int(a[6:8]))
    d1 = date(int(b[:4]), int(b[4:6]), int(b[6:8]))
    while d0 <= d1:
        yield d0.strftime("%Y%m%d")
        d0 += timedelta(days=1)


def main() -> None:
    ap = argparse.ArgumentParser(description="競馬ブック地方 調教 日次コレクター")
    ap.add_argument("--from", dest="d_from", required=True, help="YYYYMMDD")
    ap.add_argument("--to", dest="d_to", required=True, help="YYYYMMDD")
    ap.add_argument("--places", nargs="*", default=None, help="場名フィルタ（例: 川崎 浦和 船橋 大井）")
    ap.add_argument("--out-dir", default="data/samples")
    ap.add_argument("--tag", default=None, help="出力ファイル名の接頭辞（例: urawa → keibabook_chokyo_urawa_YYYYMMDD.jsonl。会場別に分けて衝突回避）")
    ap.add_argument("--sleep", type=float, default=1.8, help="fetch間隔秒(既定1.8)")
    ap.add_argument("--max-races", type=int, default=None, help="1日の最大レース数(動作確認用)")
    ap.add_argument("--overwrite", action="store_true", help="既存の日ファイルも取り直す")
    ap.add_argument("--force", action="store_true", help="Cookie失効検出でも続行")
    args = ap.parse_args()

    if not os.environ.get("KEIBABOOK_COOKIE"):
        print("⚠️ KEIBABOOK_COOKIE 未設定。会員Cookieが要ります（非会員は先頭馬のみ）。", file=sys.stderr)
    os.makedirs(args.out_dir, exist_ok=True)
    total_races = total_horses = 0

    for ymd in daterange(args.d_from, args.d_to):
        pref = f"{args.tag}_" if args.tag else ""
        out = os.path.join(args.out_dir, f"keibabook_chokyo_{pref}{ymd}.jsonl")
        if os.path.exists(out) and not args.overwrite:
            print(f"[{ymd}] スキップ(既存)"); continue
        try:
            races = kb.race_ids_for_date(ymd)
        except Exception as e:
            print(f"[{ymd}] nittei失敗: {e}"); time.sleep(args.sleep); continue
        if not races:
            print(f"[{ymd}] 開催なし"); continue

        # 会場フィルタ（id[8:10]は会場でなく開催indexなので、nitteiの会場名で判定）
        keep_ids = [r for r in races if (not args.places) or (r.get("place") in args.places)]
        keep_ids.sort(key=lambda x: (x.get("place") or "", x["race_no"]))
        if not keep_ids:
            print(f"[{ymd}] 対象会場なし"); continue
        if args.max_races:
            keep_ids = keep_ids[:args.max_races]

        recs, cookie_ok = [], None
        for r in keep_ids:
            try:
                rec = kb.chokyo_race(r["id"])
            except Exception as e:
                print(f"  {r['id']} 取得失敗: {e}"); time.sleep(args.sleep); continue
            nh = len(rec.get("horses", []))
            # Cookie失効検出: 頭数1のレースが続く＝非会員/失効の疑い
            if cookie_ok is None:
                cookie_ok = nh > 1
                if not cookie_ok and not args.force:
                    print(f"  ⚠️ {rec.get('place')}{rec.get('race_no')}R が{nh}頭のみ＝Cookie未設定/失効の疑い。"
                          f"中断します（続行は --force）。", file=sys.stderr)
                    return
            recs.append(rec)
            total_horses += nh
            print(f"  {rec.get('place','?')}{rec.get('race_no','?')}R {nh}頭")
            time.sleep(args.sleep)

        if recs:
            with open(out, "w", encoding="utf-8") as f:
                for rec in recs:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            total_races += len(recs)
            print(f"[{ymd}] 保存 {len(recs)}レース → {out}")

    print(f"\n完了: {total_races}レース / 延べ{total_horses}頭")


if __name__ == "__main__":
    main()
