"""当日の『決着時計トレンド』を表示し、予想モード(消耗戦/通常)の指針を出す。

南関の馬場は時間とともに乾いて速くなる(またはさらに雨で悪化する)。レースごとの
決着時計を距離標準化(秒/1000m)して並べることで、「今このレースは時計がかかる
消耗戦か / 乾いて速くなっているか」を読み、predict_nankan.py の --mode と --baba を
当てる判断材料にする。

実行例:
    python3 scripts/track_trend.py --date 2026-06-03 --place 船橋
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD_URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"
RESULT_URL = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{race_id}"


def _t2s(t: str | None) -> float | None:
    if not t or ":" not in t:
        return None
    m, s = t.split(":")
    return int(m) * 60 + float(s)


def main() -> None:
    ap = argparse.ArgumentParser(description="当日の決着時計トレンド")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", choices=list(NANKAN_CODES), required=True)
    args = ap.parse_args()
    ymd = args.date.replace("-", "")
    code = NANKAN_CODES[args.place]

    client = PoliteClient()
    idx = client.get(CARD_URL.format(race_id=day_index_race_id(ymd, args.place)))
    races = P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=code)

    print(f"\n=== {args.place} {args.date} 決着時計トレンド ===")
    print(f"{'R':>3}{'発走':>6}{'距離':>7}{'天候':>4}{'馬場':>4}{'決着':>8}"
          f"{'秒/1000m':>9}{'勝人気':>6}")
    rows = []
    for rno, rid in races:
        try:
            html = client.get(RESULT_URL.format(race_id=rid), use_cache=False)
            res = P.parse_result_page(html, rid)
        except Exception:  # noqa: BLE001
            continue
        if not res.rows:
            print(f"{rno:>3}{'':>6}   --- 以降は発走前 ---")
            break
        cond = P.parse_conditions(html)
        win = res.rows[0]
        sec = _t2s(win.time)
        idx100 = sec / res.distance * 1000 if sec and res.distance else None
        rows.append((rno, res.distance, cond, sec, idx100, win))
        print(f"{rno:>3}{(cond['post_time'] or ''):>6}{res.surface+str(res.distance)+'m':>7}"
              f"{(cond['weather'] or ''):>4}{(cond['baba_full'] or ''):>4}{(win.time or ''):>8}"
              f"{(f'{idx100:.1f}' if idx100 else ''):>9}{str(win.popularity):>6}")

    if len(rows) >= 2:
        _trend(rows)


def _trend(rows) -> None:
    last = rows[-1]
    prev = rows[-2]
    same = [r for r in rows[:-1] if r[1] == last[1]]
    print("\n--- 判定 ---")
    baba = last[2]["baba"]
    direction = None
    if same:
        d = last[4] - same[-1][4]
        direction = "速くなった(乾き)" if d < -0.3 else ("遅くなった(悪化)" if d > 0.3 else "横ばい")
        print(f"同距離({last[1]}m)直近比: {d:+.1f}秒/1000m → {direction}")
    else:
        d = last[4] - prev[4]
        print(f"前走比(距離違い・参考): {d:+.1f}秒/1000m")

    slow = baba in ("重", "不") and (not same or direction != "速くなった(乾き)")
    if slow:
        print(f"推奨: 消耗戦モード(--mode shomousen --baba {baba})  "
              "→ タフネス・短間隔(連闘/叩き)を重視")
    else:
        print(f"推奨: 通常モード(--mode normal --baba {baba or '稍'})  "
              "→ 能力・速い持ち時計を重視(乾いてきたら速時計型を見直す)")


if __name__ == "__main__":
    main()
