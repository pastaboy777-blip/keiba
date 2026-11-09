"""調教(追い切り)アナライザ ── 穴馬の"追い切り好転"を全頭スコア化。
competitorブック地方 /chihou/cyokyo/1/0/{rid} を解析。1テーブル内に全頭が
[ヘッダ行(馬番/馬名/総評/矢印)] + [明細テーブル(cyokyodata)] の対で並ぶ。

抽出:
  arrow  … 矢印 ↑/→/↓  (競馬ブックの気配方向 = 直接シグナル)
  soukan … 総評(手控え/仕上がる 等)
  最新追い切り: 末3F(half/f3)・末1F(f1)時計, 脚色(一杯/強目/馬也/余力), 行短評
スコア(調教だけで):
  +2 矢印↑ / -2 矢印↓
  +2 一杯に追って好時計(末1F 12.5秒以下 等) = 動いた
  +1 併せ先着/馬体良化/動き上々 等ポジ短評
  -1 手控え/平凡/案外 等ネガ
穴サイン: 人気薄(単勝オッズ順で下位) かつ 調教スコア>=2 → ★追い切り好転の穴候補
標準ライブラリ + curl(kb.conf)。
"""
import subprocess, re, os, sys
SP = os.path.dirname(os.path.abspath(__file__))
ARC = os.path.join(SP, "arc"); os.makedirs(ARC, exist_ok=True)
BASE = "https://p.keibabook.co.jp"

POS = ["動き上々", "動きは上々", "動き良く", "動きが良", "上々", "良化", "気配良", "馬体良", "絞れ",
       "先着", "しっかり", "力強", "весь", "抜群", "文句なし", "好調", "上向", "渋太", "反応良", "格段"]
NEG = ["手控え", "平凡", "案外", "物足り", "地味", "行き脚つかず", "重目", "太め", "нет", "一息",
       "ソラ", "頼りな", "見劣", "footが", "だく", "だけ"]

def _get(url, out):
    if not os.path.exists(out) or os.path.getsize(out) < 800:
        subprocess.run(["curl", "-s", "-L", "-K", os.path.join(SP, "kb.conf"), url, "-o", out], check=False)
    return out

def _txt(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()

def parse(rid):
    """rid -> {umaban:{name,umacd,arrow,soukan,last:{f3,f1,ashiiro,note}}}"""
    f = _get(f"{BASE}/chihou/cyokyo/1/0/{rid}", os.path.join(ARC, f"cyo_{rid}.html"))
    h = open(f, encoding="utf-8", errors="replace").read()
    # split into per-horse chunks at each header row
    heads = list(re.finditer(
        r'<td class="umaban">(\d+)</td><td class="kbamei"><a href="/db/uma/(\d+)"[^>]*>([^<]+)</a></td>'
        r'<td class="tanpyo">([^<]*)</td><td class="yajirusi"><span[^>]*>([^<]*)</span>', h))
    out = {}
    for i, m in enumerate(heads):
        ub = int(m.group(1)); umacd = m.group(2); name = m.group(3)
        soukan = m.group(4).strip(); arrow = m.group(5).strip()
        seg = h[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(h)]
        # detail rows: each <tr> in cyokyodata; latest = first data row with a time
        last = None
        for rm in re.finditer(r"<tr>(.*?)</tr>", seg, re.S):
            cells = [_txt(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", rm.group(1), re.S)]
            if len(cells) < 14:
                continue
            times = [c for c in cells[5:12] if re.match(r"^\d{1,3}\.\d$", c)]
            ashiiro = cells[13] if len(cells) > 13 else ""
            note = cells[14] if len(cells) > 14 else ""
            if not times and not ashiiro:
                continue
            # last 1F is the final time token
            f1 = float(times[-1]) if times else None
            f3 = float(times[-2]) if len(times) >= 2 else None
            last = {"f3": f3, "f1": f1, "ashiiro": ashiiro, "note": note}
            break
        out[ub] = {"name": name, "umacd": umacd, "arrow": arrow, "soukan": soukan, "last": last}
    return out

def score(rec):
    """1頭の調教レコード -> (score, tags)"""
    sc = 0.0; tags = []
    ar = rec.get("arrow", "")
    if ar in ("↑", "⤴", "&uarr;") or "↑" in ar: sc += 2; tags.append("矢印↑")
    if ar in ("↓", "⤵") or "↓" in ar: sc -= 2; tags.append("矢印↓")
    last = rec.get("last") or {}
    f1 = last.get("f1"); ashi = last.get("ashiiro", "")
    # 一杯/強目で速い末1F = 動いた ; 馬也/余力で速い = 抜群の余裕
    if f1 is not None:
        if f1 <= 12.6 and ("一杯" in ashi or "強目" in ashi or "強め" in ashi):
            sc += 2; tags.append(f"一杯で好時計(末1F{f1})")
        elif f1 <= 12.4 and ("馬也" in ashi or "余力" in ashi or "馬なり" in ashi):
            sc += 2.5; tags.append(f"馬なり余力の好時計(末1F{f1})")
        elif f1 <= 13.0:
            sc += 0.5; tags.append(f"末1F{f1}")
    note = (last.get("note", "") or "") + " " + rec.get("soukan", "")
    if any(w in note for w in POS): sc += 1; tags.append("ポジ短評")
    if any(w in note for w in NEG): sc -= 1; tags.append("ネガ短評")
    return sc, tags

def odds_rank(rid):
    o = os.path.join(ARC, f"tan_{rid}.html")
    _get(f"{BASE}/chihou/odds/0/{rid}", o)
    h = open(o, encoding="utf-8", errors="replace").read()
    od = {}
    for m in re.finditer(r"umaban[^>]*>(\d+)<.*?(\d+\.\d)", h, re.S):
        ub = int(m.group(1))
        if ub not in od: od[ub] = float(m.group(2))
    rank = {ub: i + 1 for i, (ub, _) in enumerate(sorted(od.items(), key=lambda x: x[1]))}
    return od, rank

def analyze(rid, unpop_from=6):
    recs = parse(rid); od, rank = odds_rank(rid)
    rows = []
    for ub, rec in recs.items():
        sc, tags = score(rec)
        pk = rank.get(ub, 99)
        ana = "★追い切り好転の穴" if (pk >= unpop_from and sc >= 2) else ""
        rows.append((sc, ub, rec["name"], pk, od.get(ub), rec["arrow"], tags, ana))
    rows.sort(key=lambda x: (-x[0], x[3]))
    return rows

if __name__ == "__main__":
    rid = sys.argv[1]
    print(f"=== 追い切りスコア {rid} ===")
    for sc, ub, nm, pk, o, ar, tags, ana in analyze(rid):
        star = " " + ana if ana else ""
        print(f"  {sc:+.1f} | {ub:2}番 {nm} | {pk}人{o} | {ar} | {'/'.join(tags)}{star}")
