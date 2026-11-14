"""レースが終わった日の「予想と結果の検証」を1本で出す(中央)。その1日だけを見る。

    python3 scripts/jra_kensho.py --date 2026-11-14
    python3 scripts/jra_kensho.py --date 2026-11-15 --fetch            # 先に当日の結果を JRA公式から取り込む
    python3 scripts/jra_kensho.py --date 2026-11-15 --toujitsu         # 当日の前の鞍の結果も使った予想で照らす
    python3 scripts/jra_kensho.py --date 2026-11-15 --baba 福島=稍     # 予想に使う馬場を手で決める

予想の作り方
  展開図(scripts/jra_tenkai_zu.py)の one_race をそのまま呼ぶ。材料は
    races.jsonl のうち「その日より前」の鞍 + 出馬表(data/jra/shutuba_YYYYMMDD.jsonl)の行。
  その日の結果の行は予想の材料に入れない(from_data は同じ race_id の最初の行を使うので、
  結果の行が混ざるとその鞍の頭数・馬場・馬体重が結果側になる。当日の前の鞍のずれも入ってしまう)。
  --toujitsu のときだけ、当日のその鞍より前の鞍の結果を足す(当日の昼に作り直した展開図と同じ材料)。
  馬場は既定で当日の発表(結果の行の馬場)。--baba / --baba-dirt で上書き(書式は jra_morning.py と同じ)。

実際のペース
  pace_of(lap, distance)["diff"] を、展開図と同じ境目 q(その日より前の全鞍の3等分)で切る。

出すもの(notes/live/YYYYMMDD_jra_kensho_auto.md と画面)
  1 全体: ペース3区分の当たり・外れ方の内訳・1角/4角の順位相関(新馬は別)・ハナ1頭目/上位3頭(新馬除く)
  2 場×芝ダ: 3着内の馬の4角の位置(前1/3・中・後ろ)と、4角の組の外にいた割合(その日だけ)
  3 丸を付けた鞍(scripts/daily/marks_YYYYMMDD.json): 赤丸・白丸の馬の着順
  4 鞍ごとの一覧
人気は表に「何番人気が来たか」を出すだけで、評価には使わない。過去の開催と比べる集計はしない。
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import io
import json
import re
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

MARU = "⓪①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
BABA_NORM = {"良": "良", "稍": "稍", "稍重": "稍", "重": "重", "不": "不", "不良": "不"}
PACE_SHORT = {"スロー": "S", "ミドル": "M", "ハイ": "H"}


def maru(u):
    return MARU[u] if isinstance(u, int) and 0 < u < len(MARU) else str(u)


def read_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def parse_baba(s):
    out = {}
    for part in filter(None, (s or "").replace("、", ",").split(",")):
        k, _, v = part.partition("=")
        if v.strip() not in BABA_NORM:
            sys.exit(f"馬場が読めません: {part}(良/稍/重/不)")
        out[k.strip()] = BABA_NORM[v.strip()]
    return out


def is_shogai(d):
    """障害の鞍(公式の結果では芝として入っている。race_type/名前で見分ける)。"""
    return (d.get("surface") == "障" or "障害" in (d.get("race_type") or "") or "障害" in (d.get("name") or "")
            or "ジャンプ" in (d.get("name") or ""))


def is_shinba(d):
    return (d.get("race_class") or "").startswith("新馬") or "新馬" in (d.get("name") or "")


def fetch(date):
    """jra_today.py の取り込み部分と同じ。終わった鞍を races.jsonl に足す(済みは飛ばす)。展開図は作り直さない。"""
    import jra_official_harvest as Hv
    from nankeiba.scraping.jra_official import links, month_checksums, parse_race, race_id_of
    ymd = date.replace("-", "")
    data = ROOT / "data" / "jra" / "races.jsonl"
    have = {json.loads(l)["race_id"] for l in open(data) if l.strip()}
    f = Hv.Fetcher(3.0)
    ck = month_checksums(f.post(Hv.SEARCH))
    new = 0
    with data.open("a", encoding="utf-8") as fo:
        for day in links(f.post(f"pw01skl00{ymd[:6]}/{ck[ymd[2:6]]}"), "pw01srl"):
            if ymd not in day:
                continue
            for c in links(f.post(day), "pw01sde"):
                rid = race_id_of(c)
                if not rid or c[-11:-3] != ymd or rid in have:
                    continue
                d = parse_race(f.post(c), rid)
                if d and d["result"] and all(r.get("time") for r in d["result"][:3]) and d.get("lap"):
                    fo.write(json.dumps(d, ensure_ascii=False) + "\n")
                    have.add(rid)
                    new += 1
                    print("結果", d["place"], int(rid[-2:]), "R", flush=True)
    print(f"新しく取り込んだ鞍 {new}")


def corner_groups(d, key="4"):
    """通過順の文字列 → 組(かっこ・単独)のリスト。かっこの中は内から。"""
    s = ((d.get("corners") or {}).get(key) or "").replace("*", "")
    return [[int(x) for x in re.findall(r"\d+", t)] for t in re.findall(r"\([^)]*\)|\d+", s)]


def lane_of(groups, u):
    for g in groups:
        if u in g:
            if len(g) < 2:
                return "単"
            return "外" if g[-1] == u else "内" if g[0] == u else "中"
    return None


def zone_of(c4, n):
    if not c4 or n < 2:
        return None
    r = (c4 - 1) / (n - 1)
    return "前" if r <= 1 / 3 else ("中" if r <= 2 / 3 else "後")


def predict_day(date, races, shutuba, *, toujitsu, baba_t, baba_d, tmp):
    """その日の鞍ごとに展開図の予想を作る。返り値 {race_id: {fc, rows}}"""
    import jra_tenkai_zu as Z
    import jra_learn as J  # noqa: F401  (rank_corr 用。import できることを先に確かめる)
    res_today = {d["race_id"]: d for d in races if d["date"] == date}
    with open(tmp, "w", encoding="utf-8") as fo:
        # 出馬表を先に書く: from_data は同じ race_id の最初の行をその鞍として使う
        for d in shutuba:
            d = dict(d)
            r = res_today.get(d["race_id"])
            p = d["place"]
            if d.get("surface") == "ダ" and p in baba_d:
                d["baba"] = baba_d[p]
            elif p in baba_t:
                d["baba"] = baba_t[p]
            elif r and r.get("baba"):
                d["baba"] = r["baba"]   # 当日の発表
            fo.write(json.dumps(d, ensure_ascii=False) + "\n")
        for d in races:
            if d["date"] < date or (toujitsu and d["date"] == date):
                fo.write(json.dumps(d, ensure_ascii=False) + "\n")

    captured = {}
    orig_build = Z.build

    def build_spy(*a, **k):
        fc, rows, rk = orig_build(*a, **k)
        captured["rows"] = rows
        return fc, rows, rk

    Z.build = build_spy
    out = {}
    sb_ids = {d["race_id"] for d in shutuba}
    for rid in sorted(res_today):
        d = res_today[rid]
        if d.get("surface") not in ("芝", "ダ") or is_shogai(d):
            continue
        if rid not in sb_ids:
            print(f"  出馬表に無いので飛ばす: {rid}", file=sys.stderr)
            continue
        a = argparse.Namespace(race_id=rid, shutuba=None, past=None, date=date, place=None, race_no=str(int(rid[-2:])),
                               day=None, out="x", jockey_stats=None, from_data=True, style="kawa", zone_front=0.4,
                               pace_data=str(tmp), circle="", circle2="", circle_each=False, hide_pace="",
                               base_day=None, base_baba=None, base_day_dirt=None, base_baba_dirt=None,
                               base_time=None, kikou=False, no_trend=True)
        captured.clear()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                _, place, rno, fc = Z.one_race(a, None)
        except Exception as e:  # noqa: BLE001
            print(f"  予想を作れなかった {rid}: {e!r}", file=sys.stderr)
            continue
        out[rid] = {"fc": fc, "rows": captured.get("rows", [])}
    Z.build = orig_build
    return out


def evaluate(d, pr):
    """1鞍の予想 pr と結果 d を照らす。"""
    import jra_learn as J
    from nankeiba.scraping.db_race import pace_of
    fc, rows = pr["fc"], pr["rows"]
    n = d["field_size"]
    act1 = {x["umaban"]: x["corner_pos"][0] for x in d["result"] if x.get("corner_pos")}
    act4 = {x["umaban"]: x["corner_pos"][-1] for x in d["result"] if x.get("corner_pos")}
    e = {"race_id": d["race_id"], "place": d["place"], "R": int(d["race_id"][-2:]), "surface": d["surface"],
         "dist": d["distance"], "baba": d.get("baba"), "n": n, "shinba": is_shinba(d), "name": d.get("name") or "",
         "pace_pred": getattr(fc, "pace", None), "diff_pred": getattr(fc, "diff_pred", None),
         "rel": (fc.rel[0] if getattr(fc, "rel", None) else None)}
    q = getattr(fc, "q", None)
    pc = pace_of(d.get("lap") or [], d["distance"])
    if pc and q:
        e["diff_act"] = pc["diff"]
        e["pace_act"] = "ハイ" if pc["diff"] < q[0] else ("スロー" if pc["diff"] > q[1] else "ミドル")
    for key, act, lab in (("pos1", act1, "c1"), ("pos", act4, "c4")):
        pp = [r for r in rows if r.get(key) is not None and r["ub"] in act]
        if len(pp) >= 5:
            e[lab] = J.rank_corr([-r[key] for r in pp], [act[r["ub"]] for r in pp])
    lead = sorted(u for u, c in act1.items() if c == 1)
    e["lead_act"] = lead
    hn = [r["ub"] for r in sorted([r for r in rows if "hana" in r], key=lambda r: -r["hana"])]
    e["hana_pred"] = hn[:3]
    if hn and lead:
        e["hana1"] = hn[0] in lead
        e["hana3"] = bool(set(hn[:3]) & set(lead))
    order = list(getattr(fc, "order", []) or [])
    e["order_pred"] = order[:3]
    if order and lead:
        e["order1"] = order[0] in lead
        e["order3"] = bool(set(order[:3]) & set(lead))
    g4 = corner_groups(d, "4")
    top = []
    for x in d["result"]:
        if (x.get("finish_pos") or 99) <= 3:
            c4 = x["corner_pos"][-1] if x.get("corner_pos") else None
            top.append({"fin": x["finish_pos"], "ub": x["umaban"], "name": x["horse_name"], "c4": c4,
                        "zone": zone_of(c4, n), "lane": lane_of(g4, x["umaban"]), "nin": x.get("popularity")})
    e["top"] = sorted(top, key=lambda t: (t["fin"], t["ub"]))
    e["fin"] = {x["umaban"]: x.get("finish_pos") for x in d["result"]}
    return e


def pct(a, b):
    return f"{a}/{b}" + (f"({a / b:.0%})" if b else "")


def mean_s(v):
    return f"{st.mean(v):+.2f}(n={len(v)})" if v else "-"


def parse_marks(path):
    """marks_YYYYMMDD.json → [(場, R, 種別, {馬番})]"""
    if not path or not Path(path).exists():
        return []
    m = json.load(open(path, encoding="utf-8"))
    out = []
    for p, v in m.items():
        if p == "split" or not isinstance(v, dict):
            continue
        for key, lab in (("circle", "赤丸"), ("circle2", "白丸")):
            for part in filter(None, (v.get(key) or "").split(";")):
                rr, _, uu = part.partition(":")
                out.append((p, int(rr), lab, [int(x) for x in uu.split(",") if x.strip()]))
    for s in m.get("split") or []:
        for key, lab in (("yaya", "稍重版の丸"), ("omo", "重版の丸")):
            if s.get(key):
                out.append((s["place"], int(s["race"]), lab, [int(x) for x in str(s[key]).split(",") if x.strip()]))
    return out


def report(date, E, marks, *, toujitsu, missing):
    L = []
    w = L.append
    mode = "当日のその鞍より前の結果も使った予想" if toujitsu else "その日より前のデータ＋出馬表だけの予想(馬場は当日の発表)"
    w(f"# {date} 中央 予想と結果の検証(自動、scripts/jra_kensho.py)\n")
    w(f"- 予想: 展開図(jra_tenkai_zu.one_race)の {mode}")
    w(f"- 鞍数 {len(E)}(芝・ダ、障害除く。ラップの無い鞍はペースの数に入らない)" + (f"。予想を作れなかった鞍 {len(missing)}: {', '.join(missing)}" if missing else ""))
    w("- その日だけの集計。過去の開催との比較はしない。人気は表に出すだけで評価には使わない。\n")

    # 1 全体
    w("## 1. 全体\n")
    pe = [e for e in E if e.get("pace_act") and e.get("pace_pred")]
    hit = sum(e["pace_pred"] == e["pace_act"] for e in pe)
    w(f"- ペース3区分(スロー/ミドル/ハイ) 当たり **{pct(hit, len(pe))}**")
    miss = collections.Counter((e["pace_pred"], e["pace_act"]) for e in pe if e["pace_pred"] != e["pace_act"])
    if miss:
        w("- 外れ方(予想→実際): " + "、".join(
            f"{a}→{b} {c}鞍({'・'.join(e['place'] + str(e['R']) + 'R' for e in pe if (e['pace_pred'], e['pace_act']) == (a, b))})"
            for (a, b), c in miss.most_common()))
    dd = [e["diff_act"] - e["diff_pred"] for e in pe if e.get("diff_pred") is not None]
    if dd:
        w(f"- 前後半差のずれ(実−予) 平均 {st.mean(dd):+.2f}秒(＋は実のほうが後半速い＝前半ゆるい)")
    for lab, f in (("新馬除く", lambda e: not e["shinba"]), ("新馬", lambda e: e["shinba"])):
        g = [e for e in E if f(e)]
        c1, c4 = [e["c1"] for e in g if "c1" in e], [e["c4"] for e in g if "c4" in e]
        if g and not (c1 or c4):
            w(f"- 隊列の順位相関({lab} {len(g)}鞍) 過去走が無いので出ない")
        elif g:
            w(f"- 隊列の順位相関({lab}) 最初のコーナー(1角) {mean_s(c1)}・4角 {mean_s(c4)}")
    g = [e for e in E if not e["shinba"]]
    o1 = [e["order1"] for e in g if "order1" in e]
    o3 = [e["order3"] for e in g if "order3" in e]
    w(f"- ハナ(新馬除く、展開図の先頭候補 fc.order の順) 1頭目が当たり **{pct(sum(o1), len(o1))}**・上位3頭に入った **{pct(sum(o3), len(o3))}**")
    h1 = [e["hana1"] for e in g if "hana1" in e]
    h3 = [e["hana3"] for e in g if "hana3" in e]
    w(f"- 参考: ハナ専用モデル(r[\"hana\"])の順だと 1頭目 {pct(sum(h1), len(h1))}・上位3頭 {pct(sum(h3), len(h3))}\n")

    # 2 場×芝ダ
    w("## 2. 場×芝ダ 3着内の馬の4角(その日だけ)\n")
    w("| 場 | 芝ダ | 鞍 | 3着内 | 4角 前1/3 | 中 | 後ろ | 組の外 | 内 | 中ほど | 単独 |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    grp = collections.defaultdict(list)
    for e in E:
        grp[(e["place"], e["surface"])].append(e)
    for (p, s), es in sorted(grp.items()):
        tops = [t for e in es for t in e["top"]]
        z = collections.Counter(t["zone"] for t in tops if t["zone"])
        nz = sum(z.values())
        ln = collections.Counter(t["lane"] for t in tops if t["lane"])
        ng = ln["外"] + ln["内"] + ln["中"]
        f = lambda c, n: f"{c}({c / n:.0%})" if n else "-"  # noqa: E731
        w(f"| {p} | {s} | {len(es)} | {len(tops)} | {f(z['前'], nz)} | {f(z['中'], nz)} | {f(z['後'], nz)} | "
          f"{f(ln['外'], ng)} | {f(ln['内'], ng)} | {f(ln['中'], ng)} | {ln['単']} |")
    w("\n組の外/内/中ほど は4角で2頭以上の組(かっこ)にいた3着内の馬の中での割合(かっこの中は内から)。単独は組に入っていない馬。\n")

    # 3 丸
    w("## 3. 丸を付けた鞍\n")
    byk = {(e["place"], e["R"]): e for e in E}
    if not marks:
        w("なし(marks ファイルが無い)\n")
    else:
        w("| 場R | 丸 | 馬(着順) | 3着内 |")
        w("|---|---|---|---|")
        for p, r, lab, us in marks:
            e = byk.get((p, r))
            if not e:
                w(f"| {p}{r}R | {lab} | 結果なし | - |")
                continue
            fs = [(u, e["fin"].get(u)) for u in us]
            w(f"| {p}{r}R | {lab} | " + " ".join(f"{maru(u)}{f if f else '取消'}着" if f else f"{maru(u)}-" for u, f in fs)
              + f" | {sum(1 for _, f in fs if f and f <= 3)}/{len(us)} |")
        w("")

    # 4 一覧
    w("## 4. 鞍ごと\n")
    w("| 場R | コース | 馬場 | 頭 | ペース 予→実 | 前後差 予/実 | 1角相関 | 4角相関 | ハナ 予→実 | 1着 | 2着 | 3着 | 人気 |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for e in sorted(E, key=lambda e: (e["place"], e["R"])):
        pa = (f"{e['pace_pred'] or '-'}→{e.get('pace_act') or '-'}" + (" ○" if e.get("pace_act") and e["pace_pred"] == e["pace_act"] else ""))
        df = (f"{e['diff_pred']:+.1f}/{e['diff_act']:+.1f}" if e.get("diff_pred") is not None and "diff_act" in e else "-")
        hp = "".join(maru(u) for u in e["order_pred"][:3]) if not e["shinba"] and e["order_pred"] else "-"
        ha = "".join(maru(u) for u in e["lead_act"]) or "-"
        hk = "" if e["shinba"] else (" ◎" if e.get("order1") else (" ○" if e.get("order3") else ""))
        tops = {}
        for t in e["top"]:
            tops.setdefault(t["fin"], []).append(f"{maru(t['ub'])} 4角{t['c4'] or '-'}" + (f"{t['lane']}" if t["lane"] and t["lane"] != "単" else ""))
        nin = "-".join(str(t["nin"] or "?") for t in e["top"])
        w(f"| {e['place']}{e['R']}R | {e['surface']}{e['dist']}{' 新馬' if e['shinba'] else ''} | {e['baba'] or '-'} | {e['n']} | {pa} | {df} | "
          f"{('%+.2f' % e['c1']) if 'c1' in e else '-'} | {('%+.2f' % e['c4']) if 'c4' in e else '-'} | {hp}→{ha}{hk} | "
          + " | ".join("・".join(tops.get(k, ["-"])) for k in (1, 2, 3)) + f" | {nin} |")
    w("\nハナ: 予は展開図の先頭候補(fc.order)の上位3頭(新馬は出さない)、実は1角先頭。◎=1頭目が当たり、○=上位3頭に入った。"
      "1〜3着は 馬番・4角の通過順位・組の中の位置(外/内/中)。人気は1着-2着-3着の順。")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--data", default=str(ROOT / "data" / "jra" / "races.jsonl"))
    ap.add_argument("--shutuba", help="出馬表(省略で data/jra/shutuba_YYYYMMDD.jsonl)")
    ap.add_argument("--marks", help="丸(省略で scripts/daily/marks_YYYYMMDD.json があれば読む)")
    ap.add_argument("--fetch", action="store_true", help="先に当日の結果を JRA公式から races.jsonl に取り込む")
    ap.add_argument("--toujitsu", action="store_true", help="当日のその鞍より前の鞍の結果も予想に使う")
    ap.add_argument("--baba", default="", help='予想に使う芝の馬場 "福島=稍,東京=良"(省略で当日の発表)')
    ap.add_argument("--baba-dirt", default="", help="同じ書式でダート")
    ap.add_argument("--out", help="省略で notes/live/YYYYMMDD_jra_kensho_auto.md")
    a = ap.parse_args()
    ymd = a.date.replace("-", "")
    if a.fetch:
        fetch(a.date)
    races = read_jsonl(a.data)
    sbp = Path(a.shutuba or ROOT / "data" / "jra" / f"shutuba_{ymd}.jsonl")
    if not sbp.exists():
        sys.exit(f"出馬表がありません: {sbp}")
    shutuba = read_jsonl(sbp)
    today = sorted((d for d in races if d["date"] == a.date and d.get("surface") in ("芝", "ダ") and not is_shogai(d)),
                   key=lambda d: d["race_id"])
    if not today:
        sys.exit(f"{a.date} の結果が {a.data} にありません(--fetch で取り込めます)")
    tmp = ROOT / "data" / "jra" / f"kensho_{ymd}.jsonl"
    baba_t = parse_baba(a.baba)
    pr = predict_day(a.date, races, shutuba, toujitsu=a.toujitsu, baba_t=baba_t,
                     baba_d={**baba_t, **parse_baba(a.baba_dirt)} if a.baba_dirt else baba_t, tmp=tmp)
    E = [evaluate(d, pr[d["race_id"]]) for d in today if d["race_id"] in pr]
    missing = [d["place"] + str(int(d["race_id"][-2:])) + "R" for d in today if d["race_id"] not in pr]
    mp = a.marks or ROOT / "scripts" / "daily" / f"marks_{ymd}.json"
    text = report(a.date, E, parse_marks(mp), toujitsu=a.toujitsu, missing=missing)
    out = Path(a.out or ROOT / "notes" / "live" / f"{ymd}_jra_kensho_auto.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    print("→", out)


if __name__ == "__main__":
    main()
