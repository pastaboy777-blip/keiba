"""競馬場ごとの1時間ごとの気温を Open-Meteo から取る(過去 archive / 予報 forecast)。

    python3 scripts/jra_kion.py --from 2023-11-01 --to 2026-11-10
    python3 scripts/jra_kion.py --forecast
→ data/jra/kion/<場>.json {"YYYY-MM-DDTHH:00": 気温℃}
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jra_wind import COURSE_LATLON, fetch  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "jra" / "kion"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2023-11-01")
    ap.add_argument("--to", default="2026-11-10")
    ap.add_argument("--forecast", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for place, (lat, lon) in COURSE_LATLON.items():
        if not a.forecast and (OUT / f"{place}.json").exists():
            continue
        if a.forecast:
            url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                   f"&hourly=temperature_2m&timezone=Asia%2FTokyo&forecast_days=7")
        else:
            url = (f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
                   f"&start_date={a.frm}&end_date={a.to}&hourly=temperature_2m&timezone=Asia%2FTokyo")
        for k in range(4):
            try:
                hz = fetch(url)["hourly"]
                break
            except Exception:  # noqa: BLE001  429 は時間をあける
                time.sleep(90 * (k + 1))
        else:
            print(place, "取れず", flush=True)
            continue
        p = OUT / f"{place}.json"
        old = json.load(open(p)) if p.exists() else {}
        old.update({t: v for t, v in zip(hz["time"], hz["temperature_2m"]) if v is not None})
        json.dump(old, open(p, "w"))
        print(place, len(old), flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
