#!/usr/bin/env python3
"""南関版・血統バカ一代＝「4代血統内に効く血(祖)を持つか」で足切り/加点する器。
サラブレの手法を南関ダートにデータ移植：各馬のnetkeiba4代血統を集合化し、
条件(場×距離帯)ごとに"その祖を4代内に持つ馬"の複勝率liftを実測。lift>=閾値かつ
十分なnの祖＝南関ダートのキーストーン血として自動抽出。daikei(大系統)より一段細かい。

正直な設計：
 - 地方馬のID解決は netkeiba 馬名検索(先頭一致)＝同名取り違えの余地あり→名前一致の弱検証を入れる。
 - 後方視の絞り込み＝チェリーピック余地。学習(--from/--to)と検証(--holdout-from/--holdout-to)を
   分けて out-of-sample で lift を測る前提(§21-H)。学習結果は json 保存し検証で再取得無しに使う。

使い方(学習):
  python3 scripts/ana/keystone.py learn --track 大井 --from 2026-04-01 --to 2026-06-30 --max-horses 200
使い方(検証・学習済キーストーンを7月に当てる):
  python3 scripts/ana/keystone.py test --track 大井 --holdout-from 2026-07-01 --holdout-to 2026-07-31
"""
import sys, re, json, argparse, datetime, urllib.parse
from pathlib import Path
from collections import defaultdict
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import netkeiba as N
from nankeiba.scraping import pedigree as PED

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
IDMAP = ROOT / "scratchpad" / "keystone_ids.json"       # 馬名->netkeiba id キャッシュ
KEYS = ROOT / "scratchpad" / "keystone_learned.json"    # 学習済キーストーン血


def band(d):
    return "短" if d <= 1200 else ("マ" if d <= 1600 else ("中" if d <= 1900 else "長"))


def load_json(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def resolve_id(nk, name, idmap):
    """馬名->netkeiba 10桁ID(キャッシュ付)。見つからなければ ''(空)を刻んで再検索を避ける。"""
    if name in idmap:
        return idmap[name] or None
    url = "https://db.netkeiba.com/?pid=horse_list&word=" + urllib.parse.quote(name)
    try:
        html = nk.get(url, use_cache=True)
        m = re.search(r"/horse/(\d{10})", html)
        hid = m.group(1) if m else ""
    except Exception:
        hid = ""
    idmap[name] = hid
    return hid or None


def ancestors4(nk, hid):
    """4代内の祖の名前集合。パス長<=4(=4代内)のみ。取得失敗は空集合。"""
    try:
        html = nk.get(PED.PED_URL.format(horse_id=hid), use_cache=True)
        anc = PED.parse_pedigree(html)
    except Exception:
        return set()
    out = set()
    for path, a in anc.items():
        if len(path) <= 4 and a.get("name"):
            out.add(a["name"].strip())
    return out


def collect(track, d0, d1, nk, idmap, max_horses=None):
    """(場,期間)の全出走を [(祖集合, 複勝good, 人気, 距離帯)] に。ped取得は1頭1回(キャッシュ)。"""
    c = PoliteClient()
    ped_cache = {}
    rows_out = []
    seen_horses = set()
    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d")
        try:
            idx = c.get(CARD.format(r=day_index_race_id(ymd, track)), use_cache=True)
            races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[track]))
        except Exception:
            races = {}
        for R, rid in sorted(races.items()):
            try:
                pc = P.parse_card_page(c.get(CARD.format(r=rid), use_cache=True), rid)
                rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
            except Exception:
                continue
            if not rr.rows or not rr.rows[0].finish_pos:
                continue
            dist = getattr(pc, "distance", None)
            if not dist:
                continue
            tb = band(dist)
            for row in rr.rows:
                if not (row.umaban and row.finish_pos and row.popularity and row.horse_name):
                    continue
                nm = row.horse_name.strip()
                if max_horses and nm not in seen_horses and len(seen_horses) >= max_horses:
                    continue  # 新規馬の取得を打ち切り(既知馬は続行)
                if nm not in ped_cache:
                    if nm not in seen_horses:
                        seen_horses.add(nm)
                    hid = resolve_id(nk, nm, idmap)
                    ped_cache[nm] = ancestors4(nk, hid) if hid else set()
                anc = ped_cache[nm]
                if not anc:
                    continue
                good = 1 if row.finish_pos <= 3 else 0
                rows_out.append((anc, good, row.popularity, tb))
    return rows_out


def aggregate(rows, usui=6):
    """祖ごとに [全体good,全体n, 人気薄good,人気薄n]。ベースも返す。"""
    base = [0, 0]; base_u = [0, 0]
    anc = defaultdict(lambda: [0, 0, 0, 0])
    for a, g, pop, tb in rows:
        base[0] += g; base[1] += 1
        u = pop >= usui
        if u:
            base_u[0] += g; base_u[1] += 1
        for name in a:
            cc = anc[name]
            cc[0] += g; cc[1] += 1
            if u:
                cc[2] += g; cc[3] += 1
    return base, base_u, anc


def cmd_learn(a, nk):
    idmap = load_json(IDMAP, {})
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    rows = collect(a.track, d0, d1, nk, idmap, a.max_horses)
    IDMAP.write_text(json.dumps(idmap, ensure_ascii=False))
    base, base_u, anc = aggregate(rows, a.usui)
    b = base[1] and base[0] / base[1]
    bu = base_u[1] and base_u[0] / base_u[1]
    print(f"=== 学習 {a.track} {a.frm}〜{a.to} 出走{base[1]}(内 人気薄{base_u[1]}) 血統取得済 ===")
    print(f" 全体ベース複勝{b:.1%} / 人気薄ベース複勝{bu:.1%}")
    keys = []
    for name, cc in anc.items():
        g, n, gu, nu = cc
        if n < a.min_n:
            continue
        lift = (g / n) / b if b else 0
        lift_u = (gu / nu) / bu if (bu and nu) else 0
        if lift >= a.min_lift and n >= a.min_n:
            keys.append({"blood": name, "n": n, "fuku": g / n, "lift": round(lift, 2),
                         "n_usui": nu, "lift_usui": round(lift_u, 2)})
    keys.sort(key=lambda k: -k["lift"])
    KEYS.write_text(json.dumps({"track": a.track, "from": a.frm, "to": a.to,
                                "base_fuku": b, "base_fuku_usui": bu, "keys": keys}, ensure_ascii=False, indent=1))
    print(f"\n[キーストーン血 候補 lift>={a.min_lift} n>={a.min_n}] 上位20")
    print(f" {'血(4代内の祖)':22s} {'複勝':>14s} {'lift':>5s} {'人気薄lift':>10s}")
    for k in keys[:20]:
        print(f" {k['blood'][:22]:22s} {k['fuku']:5.1%}({int(k['fuku']*k['n'])}/{k['n']:>3}) {k['lift']:5.2f} "
              f"{k['lift_usui']:5.2f}(n{k['n_usui']})")
    print(f"\n 学習キーストーン {len(keys)}血を {KEYS.name} に保存。test で7月に当てる。")


def cmd_test(a, nk):
    learned = load_json(KEYS, None)
    if not learned:
        raise SystemExit("学習データが無い。先に learn を実行。")
    idmap = load_json(IDMAP, {})
    keyset = {k["blood"] for k in learned["keys"]}
    d0 = datetime.date.fromisoformat(a.hfrm); d1 = datetime.date.fromisoformat(a.hto)
    rows = collect(a.track, d0, d1, nk, idmap, None)
    IDMAP.write_text(json.dumps(idmap, ensure_ascii=False))
    base, base_u, _ = aggregate(rows, a.usui)
    b = base[1] and base[0] / base[1]
    bu = base_u[1] and base_u[0] / base_u[1]
    # キーストーン血を4代内に持つ馬 vs 持たない馬
    hit = [0, 0]; hit_u = [0, 0]; non = [0, 0]
    for anc, g, pop, tb in rows:
        has = bool(anc & keyset)
        (hit if has else non)[0] += g
        (hit if has else non)[1] += 1
        if has and pop >= a.usui:
            hit_u[0] += g; hit_u[1] += 1
    print(f"=== OOS検証 {a.track} {a.hfrm}〜{a.hto}(学習={learned['from']}〜{learned['to']}) ===")
    print(f" 学習キーストーン {len(keyset)}血 / 検証出走{base[1]}")
    print(f" 全体ベース複勝 {b:.1%}")
    if hit[1]:
        print(f" キー血保有  複勝{hit[0]/hit[1]:.1%}({hit[0]}/{hit[1]}) lift{(hit[0]/hit[1])/b:.2f}")
    if non[1]:
        print(f" キー血非保有 複勝{non[0]/non[1]:.1%}({non[0]}/{non[1]}) lift{(non[0]/non[1])/b:.2f}")
    if hit_u[1]:
        print(f" キー血×人気薄 複勝{hit_u[0]/hit_u[1]:.1%}({hit_u[0]}/{hit_u[1]}) lift{(hit_u[0]/hit_u[1])/bu:.2f}(人気薄ベース{bu:.1%})")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("learn")
    lp.add_argument("--track", default="大井"); lp.add_argument("--from", dest="frm", required=True)
    lp.add_argument("--to", dest="to", required=True); lp.add_argument("--usui", type=int, default=6)
    lp.add_argument("--min-lift", type=float, default=1.15); lp.add_argument("--min-n", type=int, default=30)
    lp.add_argument("--max-horses", type=int, default=None)
    tp = sub.add_parser("test")
    tp.add_argument("--track", default="大井"); tp.add_argument("--holdout-from", dest="hfrm", required=True)
    tp.add_argument("--holdout-to", dest="hto", required=True); tp.add_argument("--usui", type=int, default=6)
    a = ap.parse_args()
    nk = N.make_client(use_cache=True)
    if a.cmd == "learn":
        cmd_learn(a, nk)
    else:
        cmd_test(a, nk)


if __name__ == "__main__":
    main()
