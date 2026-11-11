"""競馬場ごとの1時間ごとの風(風速・風向、地上10m)を Open-Meteo から取る。過去は archive、先は forecast。

    python3 scripts/jra_wind.py --from 2023-11-01 --to 2026-11-10            # 過去(10場×1回ずつ)
    python3 scripts/jra_wind.py --forecast                                    # 予報(今日から7日)

出力: data/jra/wind/<場>.json  {"YYYY-MM-DDTHH:00": [風速m/s, 風向(度, 吹いてくる方角)]}
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

COURSE_LATLON = {   # 各競馬場のおおよその位置
    "札幌": (43.0779, 141.3263), "函館": (41.7717, 140.7698), "福島": (37.7686, 140.4588),
    "新潟": (37.9506, 139.1828), "東京": (35.6617, 139.4847), "中山": (35.7271, 139.9583),
    "中京": (35.0710, 137.0260), "京都": (34.9070, 135.7270), "阪神": (34.7790, 135.3620),
    "小倉": (33.8430, 130.8740),
}
OUT = Path(__file__).resolve().parents[1] / "data" / "jra" / "wind"


def fetch(url: str) -> dict:
    import requests
    r = requests.get(url, timeout=60, headers={"User-Agent": "nankeiba-research/0.1 (personal use)"})
    r.raise_for_status()
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2023-11-01")
    ap.add_argument("--to", default="2026-11-10")
    ap.add_argument("--forecast", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for place, (lat, lon) in COURSE_LATLON.items():
        if a.forecast:
            url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                   f"&hourly=wind_speed_10m,wind_direction_10m&wind_speed_unit=ms&timezone=Asia%2FTokyo&forecast_days=7")
        else:
            url = (f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
                   f"&start_date={a.frm}&end_date={a.to}&hourly=wind_speed_10m,wind_direction_10m"
                   f"&wind_speed_unit=ms&timezone=Asia%2FTokyo")
        j = fetch(url)
        hz = j["hourly"]
        path = OUT / f"{place}.json"
        old = json.load(open(path)) if path.exists() else {}
        for t, sp, dr in zip(hz["time"], hz["wind_speed_10m"], hz["wind_direction_10m"]):
            if sp is not None and dr is not None:
                old[t] = [sp, dr]
        json.dump(old, open(path, "w"))
        print(f"{place}: {len(hz['time'])}時間ぶん → 合計 {len(old)}")
        time.sleep(1.5)


if __name__ == "__main__":
    main()
