#!/usr/bin/env python3
"""南関版・血統バカ一代（キーストーン血の自動抽出）。

サラブレ「血統バカ一代」の手法＝**「4代血統内に効く血(●)を持つか」で足切り**
（例: 宝塚記念で「サドラーズ/デピュティミニスター/ノーザンテーストを4代内に持つ馬が
過去10年全部連対」）を、南関ダートに実データ移植する:

  1. netkeiba の血統表から各馬の **4代内の祖の集合** を取る（`scraping/netkeiba.py`）。
  2. 大井ほか南関の各条件で「その祖を4代内に持つ馬」の複勝率 lift を実測。
  3. lift ≥ しきい値 かつ n 十分 の祖＝**南関ダートのキーストーン血**として自動抽出。

`core/pedigree.py` の大系統（父系の元祖）より一段細かい “4代内の祖の有無” で精度を上げる。

⚠️ 正直運用（CLAUDE.md rule4）: これは後方視の絞り込み＝多重比較でチェリーピックが出る。
   最小サンプルと lift の両方で足切りし、単勝でなく複勝軸、採用は out-of-sample で確認。
   馬名→netkeiba id は先頭一致（同名別馬の取り違えは v1 の既知の穴）。

使い方:
  python3 scripts/ana/keystone.py --places 大井 --limit 40           # 少数で試走(取得)
  python3 scripts/ana/keystone.py --places 大井 --pop-min 7 --min-n 20
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from nankeiba.scraping import rakuten as rk           # noqa: E402
from nankeiba.scraping import netkeiba                # noqa: E402
from nankeiba.core.pedigree import _normalize         # noqa: E402

NANKAN = {"大井", "川崎", "船橋", "浦和"}
CACHE = Path("data/cache/netkeiba")
IDS_JSON = CACHE / "name_to_id.json"
ANC_JSON = CACHE / "ancestors4.json"


# ---------------------------------------------------------------------------
# データ収集（楽天キャッシュ → 結果行）
# ---------------------------------------------------------------------------

@dataclass
class Outcome:
    name: str
    place: str
    dist: int | None
    baba: str | None
    finish: int
    pop: int | None
    field: int

    def is_fuku(self) -> bool:
        return self.finish <= 3          # 複勝圏の近似（南関は多頭数なので3着内で可）


def _dist_band(d: int | None) -> str:
    if not d:
        return "?"
    if d <= 1200:
        return "〜1200"
    if d <= 1500:
        return "1300-1500"
    if d <= 1800:
        return "1600-1800"
    return "1900〜"


def collect_outcomes(places: set[str], cache_glob: str) -> list[Outcome]:
    rows: list[Outcome] = []
    for pf in sorted(glob.glob(cache_glob)):
        rid = re.search(r"RACEID_(\d+)", pf).group(1)
        cf = f"data/cache/rakuten/race_card_list_RACEID_{rid}.html"
        if not os.path.exists(cf):
            continue
        try:
            chtml = open(cf, encoding="utf-8").read()
            card = rk.parse_card(chtml)
            res = rk.parse_result(open(pf, encoding="utf-8").read())
        except Exception:
            continue
        h = card["header"]
        place = h.get("place")
        if place not in places or not res:
            continue
        bm = re.search(r"(不良|稍重|重|良)", chtml)
        baba = bm.group(1) if bm else None
        field = len(res)
        for r in res:
            rows.append(Outcome(name=r["name"], place=place, dist=h.get("distance"),
                                baba=baba, finish=r["finish"], pop=r["popularity"],
                                field=field))
    return rows


# ---------------------------------------------------------------------------
# 4代内の祖 集合（netkeiba・キャッシュ付き）
# ---------------------------------------------------------------------------

def _load_json(p: Path) -> dict:
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def resolve_ancestors(names: list[str], *, limit: int | None = None,
                      maxgen: int = 4) -> dict[str, list[str]]:
    """馬名リスト → {馬名: [4代内の祖(正規化)]}。netkeibaを引きキャッシュ。"""
    CACHE.mkdir(parents=True, exist_ok=True)
    id_map = _load_json(IDS_JSON)
    anc_map = _load_json(ANC_JSON)
    nk = netkeiba.Netkeiba()
    todo = [n for n in names if n not in anc_map]
    if limit is not None:
        todo = todo[:limit]
    for i, name in enumerate(todo):
        try:
            hid = id_map.get(name)
            if hid is None:
                hid = nk.search_horse_id(name) or ""
                id_map[name] = hid
            if not hid:
                anc_map[name] = []
                continue
            ped = nk.pedigree(hid)
            anc = set()
            for g in range(1, maxgen + 1):
                for nm in ped.get(g, []):
                    z = _normalize(nm)
                    if z:
                        anc.add(z)
            anc_map[name] = sorted(anc)
        except Exception:
            anc_map[name] = anc_map.get(name, [])
        if (i + 1) % 20 == 0:
            IDS_JSON.write_text(json.dumps(id_map, ensure_ascii=False), encoding="utf-8")
            ANC_JSON.write_text(json.dumps(anc_map, ensure_ascii=False), encoding="utf-8")
            print(f"  ...解決 {i+1}/{len(todo)}", file=sys.stderr)
    IDS_JSON.write_text(json.dumps(id_map, ensure_ascii=False), encoding="utf-8")
    ANC_JSON.write_text(json.dumps(anc_map, ensure_ascii=False), encoding="utf-8")
    return anc_map


# ---------------------------------------------------------------------------
# 集計（純関数・テスト可能）
# ---------------------------------------------------------------------------

@dataclass
class Keystone:
    ancestor: str
    n: int
    fuku: int
    rate: float
    lift: float


def ancestor_lift(rows: list[Outcome], anc_by_name: dict[str, list[str]], *,
                  cond=None, min_n: int = 15, min_lift: float = 1.15
                  ) -> tuple[float, int, list[Keystone]]:
    """条件 cond に一致し祖が判明している馬で、祖ごとの複勝率 lift を出す。

    return: (baseline複勝率, 母数, [Keystone…](lift降順))
    """
    pool = [o for o in rows if o.name in anc_by_name
            and (cond is None or cond(o))]
    if not pool:
        return 0.0, 0, []
    base = sum(o.is_fuku() for o in pool) / len(pool)
    tally: dict[str, list[int]] = {}
    for o in pool:
        f = o.is_fuku()
        for a in anc_by_name[o.name]:
            t = tally.setdefault(a, [0, 0])
            t[0] += 1
            t[1] += f
    out: list[Keystone] = []
    for a, (n, fk) in tally.items():
        if n < min_n:
            continue
        rate = fk / n
        lift = rate / base if base else 0.0
        if lift >= min_lift:
            out.append(Keystone(a, n, fk, rate, lift))
    out.sort(key=lambda k: -k.lift)
    return base, len(pool), out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="南関版・血統バカ一代（キーストーン血抽出）")
    ap.add_argument("--places", nargs="+", default=["大井"])
    ap.add_argument("--cache-glob",
                    default="data/cache/rakuten/race_performance_list_RACEID_2026*.html")
    ap.add_argument("--limit", type=int, default=None,
                    help="今回netkeibaで新規解決する馬数の上限(段階取得用)")
    ap.add_argument("--pop-min", type=int, default=None, help="人気の下限(例7=人気薄のみ)")
    ap.add_argument("--dist-band", default=None, help="距離帯フィルタ(例 1600-1800)")
    ap.add_argument("--min-n", type=int, default=15)
    ap.add_argument("--min-lift", type=float, default=1.15)
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args(argv)

    places = set(args.places)
    rows = collect_outcomes(places, args.cache_glob)
    names = sorted({o.name for o in rows})
    print(f"対象: {len(places)}場 / {len(rows)}頭走 / ユニーク馬 {len(names)}")

    anc = resolve_ancestors(names, limit=args.limit)
    resolved = sum(1 for n in names if anc.get(n))
    print(f"血統解決済: {resolved}/{len(names)} 頭（--limit で段階取得）")

    def cond(o: Outcome) -> bool:
        if args.pop_min and (not o.pop or o.pop < args.pop_min):
            return False
        if args.dist_band and _dist_band(o.dist) != args.dist_band:
            return False
        return True

    base, npool, keys = ancestor_lift(rows, anc, cond=cond,
                                      min_n=args.min_n, min_lift=args.min_lift)
    tag = []
    if args.pop_min:
        tag.append(f"人気{args.pop_min}〜")
    if args.dist_band:
        tag.append(args.dist_band)
    print(f"\n=== 南関ダート キーストーン血 [{'/'.join(places)}"
          f"{' '+' '.join(tag) if tag else ''}] ===")
    print(f"母数 {npool}頭走 / baseline複勝率 {base*100:.1f}%  "
          f"(min_n≥{args.min_n}, lift≥{args.min_lift})")
    print(f"{'祖(4代内)':22}{'n':>5}{'複勝':>5}{'複勝率':>8}{'lift':>7}")
    for k in keys[:args.top]:
        print(f"{k.ancestor[:20]:22}{k.n:>5}{k.fuku:>5}{k.rate*100:>7.1f}%{k.lift:>7.2f}")
    if not keys:
        print("（該当なし＝解決済み頭数が少ないか、条件が厳しい。--limitで取得を進めて）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
