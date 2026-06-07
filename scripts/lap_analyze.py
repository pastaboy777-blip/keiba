"""楽天競馬の成績からラップを取得し、画像と同形式で分析する。

使い方(ローカル・要 requests・要ネットワーク):
    pip install -r requirements.txt

    # 5/18(月) 大井 9R〜12R を自動取得して分析(HTML + ターミナル)
    python3 scripts/lap_analyze.py --date 2026-05-18 --place 大井 --races 9-12

    # 全レース
    python3 scripts/lap_analyze.py --date 2026-05-18 --place 大井 --races all

    # ネット不可の環境向け: ハロンタイムを手入力して1レースだけ分析
    python3 scripts/lap_analyze.py --offline --distance 1600 \\
        --laps "12.7-11.6-13.5-13.3-12.0-13.1-12.7-13.3" \\
        --place 大井 --race-no 11 --date 2026-05-18

出力:
    out/lap_<date>_<place>.html  (画像相当: 表 + 200m換算グラフ)
    ターミナルにも各レースの表とサマリを表示。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.analysis import lap as L
from nankeiba.analysis import render as R


def _parse_races(spec: str) -> list[int] | None:
    """'9-12' / '9,10,11' / 'all' を [9,10,11,12] 等に。all は None。"""
    spec = spec.strip().lower()
    if spec in ("all", "*", "全"):
        return None
    out: list[int] = []
    for part in spec.replace("、", ",").split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return sorted(set(out))


def _to_racelap(rr, *, date_fallback: str = "", place_fallback: str = "") -> L.RaceLap:
    """RakutenRace → RaceLap(分析付き)。"""
    furlongs = L.parse_furlong_times(rr.furlong_str)
    analysis = L.analyze(furlongs, rr.distance or 0, reported_last_3f=rr.last_3f)
    return L.RaceLap(
        race_id=rr.race_id, place=rr.place or place_fallback, race_no=rr.race_no,
        date=rr.date or date_fallback, race_name=rr.race_name,
        surface=rr.surface, distance=analysis.distance, going=rr.going,
        weather=rr.weather, furlong_str=rr.furlong_str, analysis=analysis,
        corners=rr.corners,
    )


def run_offline(args) -> list[L.RaceLap]:
    analysis = L.analyze_str(args.laps, args.distance or 0)
    race = L.RaceLap(
        race_id=f"{args.date}_{args.place}_{args.race_no}",
        place=args.place, race_no=args.race_no, date=args.date,
        race_name=args.race_name or "", surface=args.surface, distance=analysis.distance,
        going=args.going or "", weather="", furlong_str=args.laps, analysis=analysis,
    )
    return [race]


def run_online(args) -> list[L.RaceLap]:
    from nankeiba.scraping.rakuten import RakutenClient, parse_performance

    date_compact = args.date.replace("-", "")
    client = RakutenClient(min_interval=args.interval)
    base = client.resolve_place_base(date_compact, args.place)
    if not base:
        print(f"[警告] {args.date} に {args.place} の開催が見つかりませんでした。", file=sys.stderr)
        return []
    base_no_rr = base[:-2]  # 末尾RRを除いたベース

    want = _parse_races(args.races)
    race_nos = want if want is not None else list(range(1, 13))

    races: list[L.RaceLap] = []
    for no in race_nos:
        rid = f"{base_no_rr}{no:02d}"
        try:
            html = client.fetch_performance(rid, place_base=base)
            rr = parse_performance(html, rid)
        except Exception as e:  # noqa: BLE001
            print(f"[{args.place}{no}R] 取得失敗: {e}", file=sys.stderr)
            continue
        if not rr.furlong_str:
            print(f"[{args.place}{no}R] ハロンタイムが見つかりません(未確定/未掲載?)", file=sys.stderr)
            continue
        races.append(_to_racelap(rr, date_fallback=args.date, place_fallback=args.place))
    return races


def main() -> None:
    ap = argparse.ArgumentParser(description="楽天競馬のラップを画像形式で分析")
    ap.add_argument("--date", default="", help="開催日 YYYY-MM-DD")
    ap.add_argument("--place", default="大井", help="競馬場名(例: 大井)")
    ap.add_argument("--races", default="all", help="対象レース '9-12' / '9,10' / 'all'")
    ap.add_argument("--interval", type=float, default=1.5, help="取得間隔(秒)")
    ap.add_argument("--out", default="out", help="HTML 出力ディレクトリ")
    # オフライン(手入力)モード
    ap.add_argument("--offline", action="store_true", help="ネットを使わずラップ手入力で分析")
    ap.add_argument("--laps", default="", help="ハロンタイム '12.7-11.6-...'(offline用)")
    ap.add_argument("--distance", type=int, default=0, help="距離m(offline用)")
    ap.add_argument("--race-no", type=int, default=0, dest="race_no")
    ap.add_argument("--race-name", default="", dest="race_name")
    ap.add_argument("--surface", default="ダ")
    ap.add_argument("--going", default="")
    args = ap.parse_args()

    if args.offline:
        if not args.laps:
            ap.error("--offline には --laps が必要です")
        races = run_offline(args)
    else:
        if not args.date:
            ap.error("--date が必要です(またはオフラインなら --offline --laps)")
        races = run_online(args)

    if not races:
        print("分析対象のレースがありませんでした。", file=sys.stderr)
        sys.exit(1)

    # ターミナル出力
    for race in races:
        print()
        print(R.render_text(race))

    # HTML 出力
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = (races[0].date or args.date or "lap").replace("-", "")
    place = races[0].place or args.place
    html_path = out_dir / f"lap_{tag}_{place}.html"
    title = f"{races[0].date} {place} ラップ分析"
    html_path.write_text(R.render_html(races, title=title), encoding="utf-8")
    print(f"\nHTML を書き出しました: {html_path}")


if __name__ == "__main__":
    main()
