#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""集団の記憶（H2H＝直接対決）アラート。

検証済みの事実（南関 2026/4-7月・7月ホールドアウト通過）:
  人気で劣る馬が人気馬に先着する確率
    対戦歴なし  16.7%（人気差6以上）
    過去に先着  37.3%   → +20.7pt（4-6月でも+10.2ptで再現）
  ただし H2H が予測するのは「勝つこと」でなく「あの馬より上に来ること」。
  → 使い方は【人気馬を疑う】【馬連/ワイドの相手選び】【3連単の着順】。

使い方:
  python3 scripts/ana/h2h.py build              # 対戦インデックス構築(馬名ベース)
  python3 scripts/ana/h2h.py demo               # 過去レースでの動作確認
  from h2h import alerts
  alerts([{"name":"エルツ","umaban":12,"ninki":12}, ...])
"""
import re, os, glob, json, sys
from datetime import date
from collections import defaultdict

CACHE = os.environ.get("NKCACHE",
    "/tmp/claude-0/-home-user-keiba/5c9e9520-78d2-57a1-98df-28a0a517ec92/scratchpad/nkcache")
INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "h2h_index.json")
ELO_INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "h2h_elo.json")
K_ELO = 24.0


def _parse(fn):
    t = open(fn, "rb").read().decode("euc-jp", errors="replace")
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
    hd = re.search(r"(20\d\d)年(\d+)月(\d+)日.{0,50}?(大井|川崎|船橋|浦和)", txt)
    if not hd: return None
    d = f"{hd.group(1)}-{int(hd.group(2)):02d}-{int(hd.group(3)):02d}"
    place = hd.group(4)
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        if "/horse/" not in r: continue
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if len(cells) < 15: continue
        try: chaku = int(cells[0])
        except: continue
        name = cells[3].strip()
        nk = None
        for i, c in enumerate(cells):
            if re.match(r"^\d+\.\d$", c) and i+1 < len(cells) and re.match(r"^\d+$", cells[i+1]):
                nk = int(cells[i+1]); break
        if name: rows.append((name, chaku, nk))
    return (d, place, rows) if len(rows) >= 5 else None


def build(before=None):
    """netkeibaキャッシュから馬名ベースの対戦インデックスを作る。
    before='YYYY-MM-DD' を渡すとその日より前のレースのみ（検証時のリーク防止）。"""
    races = []
    for fn in glob.glob(os.path.join(CACHE, "2026*.html")):
        if os.path.getsize(fn) < 5000: continue
        p = _parse(fn)
        if p and (before is None or p[0] < before): races.append(p)
    races.sort(key=lambda x: x[0])
    idx = defaultdict(lambda: {"a": 0, "b": 0, "last": None})
    for d, place, rows in races:
        n = len(rows)
        for i in range(n):
            for j in range(i+1, n):
                na, ca, _ = rows[i]; nb, cb, _ = rows[j]
                if na == nb: continue
                key = "\t".join(sorted([na, nb]))
                first = key.split("\t")[0]
                fc = ca if first == na else cb
                sc = cb if first == na else ca
                e = idx[key]
                if fc < sc: e["a"] += 1; e["last"] = [d, place, first]
                elif sc < fc: e["b"] += 1; e["last"] = [d, place, key.split("\t")[1]]
    out = {k: v for k, v in idx.items() if v["a"] + v["b"] > 0}
    json.dump(out, open(INDEX, "w"), ensure_ascii=False)
    # --- Elo レーティングも同時に構築（時系列順） ---
    elo = defaultdict(lambda: 1500.0)
    for d, place, rows in races:
        n = len(rows)
        for i in range(n):
            for j in range(i+1, n):
                a, ca = rows[i][0], rows[i][1]; b, cb = rows[j][0], rows[j][1]
                if ca == cb or a == b: continue
                win, lose = (a, b) if ca < cb else (b, a)
                ea = 1.0/(1.0+10**((elo[lose]-elo[win])/400.0))
                k = K_ELO/max(1, (n-1))**0.5
                elo[win] += k*(1-ea); elo[lose] -= k*(1-ea)
    json.dump({k: round(v, 1) for k, v in elo.items()}, open(ELO_INDEX, "w"), ensure_ascii=False)
    print(f"対戦インデックス構築: {len(races)}レース → {len(out)}ペア / Elo {len(elo)}頭")
    return out


_IDX = None
def _load():
    global _IDX
    if _IDX is None:
        _IDX = json.load(open(INDEX)) if os.path.exists(INDEX) else {}
    return _IDX


def h2h(name_a, name_b):
    """(a先着回数, b先着回数, 最後に先着した馬) を返す。"""
    idx = _load()
    key = "\t".join(sorted([name_a, name_b]))
    e = idx.get(key)
    if not e: return (0, 0, None)
    first = key.split("\t")[0]
    aw, bw = (e["a"], e["b"]) if first == name_a else (e["b"], e["a"])
    last = e["last"][2] if e["last"] else None
    return (aw, bw, last)


def alerts(entries, min_gap=3):
    """entries=[{name, umaban, ninki}] → 人気薄が人気馬に過去先着しているペア。
    人気差が大きいほど妙味（検証：+12〜+20pt）。"""
    res = []
    for lo in entries:
        for hi in entries:
            if lo is hi: continue
            if not lo.get("ninki") or not hi.get("ninki"): continue
            gap = lo["ninki"] - hi["ninki"]
            if gap < min_gap: continue          # lo が人気下
            w, l, _ = h2h(lo["name"], hi["name"])
            if w > l:
                res.append(dict(ana_umaban=lo.get("umaban"), ana=lo["name"], ana_ninki=lo["ninki"],
                                fav_umaban=hi.get("umaban"), fav=hi["name"], fav_ninki=hi["ninki"],
                                gap=gap, record=f"{w}-{l}",
                                lift="+20.7pt" if gap >= 6 else "+12.0pt"))
    res.sort(key=lambda x: (-x["gap"], x["ana_ninki"]))
    return res


def summarize(entries, top_ninki=5, min_gap=3):
    """レース単位の実用サマリ。
    ① 危険な人気馬：上位人気なのに、複数の人気薄から先着されている
    ② 妙味の人気薄：上位人気に土をつけた実績がある
    """
    pairs = alerts(entries, min_gap=min_gap)
    danger = defaultdict(lambda: dict(ninki=None, umaban=None, foes=[], maxgap=0))
    value = defaultdict(lambda: dict(ninki=None, umaban=None, beat=[], maxgap=0))
    for r in pairs:
        if r["fav_ninki"] <= top_ninki:          # 危険度は「上位人気が負けていた」時だけ数える
            d = danger[r["fav"]]
            d["ninki"] = r["fav_ninki"]; d["umaban"] = r["fav_umaban"]
            d["foes"].append((r["ana_ninki"], r["ana"], r["record"]))
            d["maxgap"] = max(d["maxgap"], r["gap"])
            v = value[r["ana"]]
            v["ninki"] = r["ana_ninki"]; v["umaban"] = r["ana_umaban"]
            v["beat"].append((r["fav_ninki"], r["fav"]))
            v["maxgap"] = max(v["maxgap"], r["gap"])
    dl = sorted(danger.items(), key=lambda kv: (-len(kv[1]["foes"]), -kv[1]["maxgap"]))
    vl = sorted(value.items(), key=lambda kv: (-len(kv[1]["beat"]), -kv[1]["maxgap"]))
    return dl, vl, pairs


def fmt(entries, top_ninki=5, min_gap=3, limit=4):
    dl, vl, pairs = summarize(entries, top_ninki, min_gap)
    if not pairs: return "  H2Hアラートなし（対戦の記憶に警報なし）"
    out = []
    if dl:
        out.append("  🚨【危険な人気馬】過去に人気薄から先着されている")
        for name, d in dl[:limit]:
            foes = "・".join(f"{n}人気{nm}" for n, nm, _ in sorted(d["foes"])[:3])
            mark = "⚠⚠" if len(d["foes"]) >= 3 else "⚠"
            ub = f"{d['umaban']}番 " if d["umaban"] else ""
            out.append(f"   {mark} {d['ninki']}人気 {ub}{name} ← {len(d['foes'])}頭に土 "
                       f"(最大人気差{d['maxgap']}) : {foes}")
    if vl:
        out.append("  💡【妙味の人気薄】上位人気に先着した実績")
        for name, v in vl[:limit]:
            beat = "・".join(f"{n}人気{nm}" for n, nm in sorted(v["beat"])[:3])
            ub = f"{v['umaban']}番 " if v["umaban"] else ""
            out.append(f"   ◇ {v['ninki']}人気 {ub}{name} → {beat} に先着歴({len(v['beat'])}頭)")
    out.append("  ※H2Hは『勝つ』でなく『その馬より上に来る』の情報。人気馬の取捨・相手選びに使う。")
    return "\n".join(out)


_ELO = None
def _load_elo():
    global _ELO
    if _ELO is None:
        _ELO = json.load(open(ELO_INDEX)) if os.path.exists(ELO_INDEX) else {}
    return _ELO


def elo(name):
    """その馬のEloレーティング（未知馬は1500）。"""
    return _load_elo().get(name, 1500.0)


def elo_standings(entries):
    """今日の相手に対するElo期待勝率[0,1]で全馬をランク付け。
    検証（南関1878R・今年全体・人気薄6番人気↓）:
      期待値0.60↑ = 複勝22.8% lift2.23 ／ 0.40↓ = 複勝3.9% lift0.38
      ※勝ち越し率(lift1.50)を上回る。相手の強さ＋間接推移を織り込むため、
        直接対戦のない馬にも順位がつく（発火例の3割が対戦歴ゼロ）。
    """
    out = []
    for e in entries:
        r = elo(e["name"])
        exp = [1.0/(1.0+10**((elo(o["name"])-r)/400.0)) for o in entries if o is not e]
        v = sum(exp)/len(exp) if exp else None
        # 直接勝った相手（説明用）
        beat = []
        for o in entries:
            if o is e: continue
            w, l, _ = h2h(e["name"], o["name"])
            if w > l: beat.append(o["name"])
        tier = "－" if v is None else "★ボス" if v >= 0.60 else "消" if v <= 0.40 else "中"
        out.append(dict(name=e["name"], umaban=e.get("umaban"), ninki=e.get("ninki"),
                        elo=round(r), exp=(round(v, 3) if v else None), tier=tier, beat=beat))
    out.sort(key=lambda x: -(x["exp"] if x["exp"] is not None else -1))
    return out


def fmt_elo(entries):
    """実戦出力（Elo版）。★=複勝22.8%(lift2.23) / 消=複勝3.9%(lift0.38)。"""
    st = elo_standings(entries)
    fix, judge = fixation(entries)
    out = [f"  📊 序列固定度 {fix*100:.0f}%  → {judge}"]
    boss = [s for s in st if s["tier"] == "★ボス"]
    kesi = [s for s in st if s["tier"] == "消"]
    if boss:
        out.append("  ★【Elo上位＝今日の相手より格上】複勝22.8%(lift2.23)")
        for s in boss[:4]:
            ub = f"{s['umaban']}番 " if s["umaban"] else ""
            nk = f"{s['ninki']}人気 " if s.get("ninki") else ""
            umami = " ← 人気薄で妙味大" if (s.get("ninki") or 0) >= 6 else ""
            src = f" 直接勝ち:{'・'.join(s['beat'][:3])}" if s["beat"] else " ※直接対戦なし(間接推移で検出)"
            out.append(f"    ★ {nk}{ub}{s['name']}  Elo{s['elo']} 期待{s['exp']}{umami}{src}")
    if kesi:
        out.append("  ✖【Elo下位】複勝3.9%(lift0.38)＝機械的に切る")
        for s in kesi[:5]:
            ub = f"{s['umaban']}番 " if s["umaban"] else ""
            nk = f"{s['ninki']}人気 " if s.get("ninki") else ""
            out.append(f"    ✖ {nk}{ub}{s['name']}  Elo{s['elo']} 期待{s['exp']}")
    if not boss and not kesi:
        out.append("  （Elo差が小さく判定なし）")
    return "\n".join(out)


def fixation(entries):
    """序列固定度＝出走馬の全ペアのうち、対戦歴があるペアの割合。
    検証：人気薄★ボスの複勝lift  〜10%:使用不可 / 10-25%:1.69 / 25-40%:1.20 / 40%〜:1.22"""
    names = [e["name"] for e in entries]
    tot = met = 0
    for i in range(len(names)):
        for j in range(i+1, len(names)):
            tot += 1
            w, l, _ = h2h(names[i], names[j])
            if w + l > 0: met += 1
    fix = met/tot if tot else 0.0
    if fix < 0.10:   judge = "対戦歴が薄い → この理論は使えない"
    elif fix < 0.25: judge = "★最も効くゾーン（lift1.69）"
    elif fix < 0.40: judge = "効く（lift1.20）"
    else:            judge = "序列が固まりすぎ＝市場も承知（lift1.22）"
    return fix, judge


def standings(entries, min_meets=3):
    """今日の相手に対する勝ち越しで全馬をランク付け。
    検証（人気薄・対戦3回以上, 7月ホールドアウト通過）:
      ★ボス(勝率70%↑) 複勝15.0% lift1.41 ／ 消(30%↓) 複勝7.0% lift0.66
    """
    out = []
    for e in entries:
        W = L = 0; beat = []
        for o in entries:
            if o is e: continue
            w, l, _ = h2h(e["name"], o["name"])
            W += w; L += l
            if w > l: beat.append(o["name"])
        m = W + L
        rate = (W/m) if m else None
        if m >= min_meets and rate is not None:
            tier = "★ボス" if rate >= 0.7 else "優勢" if rate >= 0.5 else "劣勢" if rate >= 0.3 else "消"
        else:
            tier = "－"
        out.append(dict(name=e["name"], umaban=e.get("umaban"), ninki=e.get("ninki"),
                        W=W, L=L, meets=m, rate=rate, tier=tier, beat=beat))
    out.sort(key=lambda x: (-(x["rate"] if x["rate"] is not None else -1), -x["meets"]))
    return out


def fmt_boss(entries, min_meets=3):
    """レース単位の実戦出力：序列固定度＋★ボス／消。"""
    fix, judge = fixation(entries)
    st = standings(entries, min_meets)
    out = [f"  📊 序列固定度 {fix*100:.0f}%  → {judge}"]
    boss = [s for s in st if s["tier"] == "★ボス"]
    kesi = [s for s in st if s["tier"] == "消"]
    if boss:
        out.append("  ★【今日の相手に勝ち越し】")
        for s in boss[:4]:
            ub = f"{s['umaban']}番 " if s["umaban"] else ""
            nk = f"{s['ninki']}人気 " if s.get("ninki") else ""
            umami = " ← 人気薄で妙味大" if (s.get("ninki") or 0) >= 6 else ""
            out.append(f"    ★ {nk}{ub}{s['name']}  {s['W']}勝{s['L']}敗({s['rate']*100:.0f}%){umami}")
    if kesi:
        out.append("  ✖【今日の相手に負け越し】機械的に評価を下げる")
        for s in kesi[:4]:
            ub = f"{s['umaban']}番 " if s["umaban"] else ""
            nk = f"{s['ninki']}人気 " if s.get("ninki") else ""
            out.append(f"    ✖ {nk}{ub}{s['name']}  {s['W']}勝{s['L']}敗({s['rate']*100:.0f}%)")
    if not boss and not kesi:
        out.append("  （対戦データ不足で序列判定なし）")
    return "\n".join(out)


def formation(entries, fav_max=5, min_gap=3):
    """H2Hを『着順の制約』に翻訳して買い目の骨格を出す。
    検証済の性質＝H2Hは"勝つ"でなく"その馬より上に来る"を予測する。
      → 降格：人気薄に土をつけられた上位人気は【1着から外す】(2-3着には残す)
      → 昇格：その人気薄を【降格馬より上の着順】に置く
    戻り値 dict: demote/promote/constraints
    """
    pairs = alerts(entries, min_gap=min_gap)
    demote = {}   # 上位人気 → 土をつけた人気薄のリスト
    promote = {}  # 人気薄 → 先着していた人気馬のリスト
    for r in pairs:
        if r["fav_ninki"] > fav_max: continue
        d = demote.setdefault(r["fav"], dict(name=r["fav"], umaban=r["fav_umaban"],
                                             ninki=r["fav_ninki"], foes=[], maxgap=0))
        d["foes"].append(r["ana"]); d["maxgap"] = max(d["maxgap"], r["gap"])
        p = promote.setdefault(r["ana"], dict(name=r["ana"], umaban=r["ana_umaban"],
                                              ninki=r["ana_ninki"], beat=[], maxgap=0))
        p["beat"].append(r["fav"]); p["maxgap"] = max(p["maxgap"], r["gap"])
    dl = sorted(demote.values(), key=lambda x: (-len(x["foes"]), -x["maxgap"]))
    pl = sorted(promote.values(), key=lambda x: (-len(x["beat"]), -x["maxgap"]))
    cons = [(r["ana"], r["ana_umaban"], r["fav"], r["fav_umaban"], r["gap"]) for r in pairs
            if r["fav_ninki"] <= fav_max]
    return dict(demote=dl, promote=pl, constraints=cons)


def fmt_formation(entries, fav_max=5, min_gap=3):
    f = formation(entries, fav_max, min_gap)
    if not f["demote"]:
        return "  H2H：買い目に効く警報なし（上位人気に土の記憶なし）"
    out = ["  🎫【H2H → 買い目の骨格】"]
    out.append("   ▼1着から外す（人気馬の降格）")
    for d in f["demote"][:3]:
        ub = f"{d['umaban']}番" if d["umaban"] else ""
        strong = "強" if len(d["foes"]) >= 2 or d["maxgap"] >= 6 else "弱"
        out.append(f"     {d['ninki']}人気 {ub}{d['name']}  ← {len(d['foes'])}頭に土(最大人気差{d['maxgap']}) [{strong}]"
                   f" → 3連単の1着から消し、2-3着で拾う")
    out.append("   ▲その上に置く（人気薄の昇格）")
    for p in f["promote"][:4]:
        ub = f"{p['umaban']}番" if p["umaban"] else ""
        tier = "1着候補にも" if p["maxgap"] >= 6 else "2-3着に厚く"
        out.append(f"     {p['ninki']}人気 {ub}{p['name']}  → {'・'.join(p['beat'][:2])}に先着歴 [{tier}]")
    out.append("   ◆守る着順（この向きで買う）")
    for a, aub, b, bub, g in sorted(f["constraints"], key=lambda x: -x[4])[:4]:
        out.append(f"     {aub or ''}{a} ＞ {bub or ''}{b}（人気差{g}）")
    return "\n".join(out)


def demo():
    """過去レースで動作確認（そのレース以前の対戦のみでインデックスを作る＝リークなし）。"""
    fn = os.path.join(CACHE, "202644072411.html")   # 大井 7/24 11R
    p = _parse(fn)
    if not p: print("demo対象が見つかりません"); return
    d, place, rows = p
    global _IDX
    _IDX = build(before=d)                          # 当日より前のみ
    entries = [dict(name=n, umaban=None, ninki=nk) for n, c, nk in rows if nk]
    print(f"\n[demo] {d} {place} 11R（実結果：1着11番ホワイトマジック/2着10番グラスグリード）")
    print(fmt(entries))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build": build()
    elif cmd == "demo": demo()
    else: print(__doc__)
