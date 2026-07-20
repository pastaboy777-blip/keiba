"""改良版 地方調教パーサ：短評・矢印・脚色・末3F(締め)時計・併せ馬結果を拾う。
大井調教行: umaban 馬名 短評 矢印 | (日付 コース 馬場 [1哩 7F 6F 5F 4F 3F 1F の時計] 脚色 短評2 ... 併せ馬)
時計は累積(5F→4F→3F...)で末尾側が締めの3F。末3F=最小の時計値を採用。
"""
import re, os, sys
import monogatari as M

BASE = M.BASE; ARC = M.ARC

def parse(rid):
    f = os.path.join(ARC, f"cyo_{rid}.html")
    M._get(f"{BASE}/chihou/cyokyo/1/0/{rid}", f)
    h = open(f, encoding="utf-8", errors="replace").read()
    heads = list(re.finditer(r'<td class="umaban">(\d+)</td><td class="kbamei"><a[^>]*>([^<]+)</a></td>'
                             r'<td class="tanpyo">([^<]*)</td><td class="yajirusi"><span[^>]*>([^<]*)</span>', h))
    out = {}
    for i, m in enumerate(heads):
        ub = int(m.group(1)); name = m.group(2); tanpyo = m.group(3).strip(); arrow = m.group(4).strip()
        seg = h[m.end(): heads[i+1].start() if i+1 < len(heads) else len(h)]
        cells = [re.sub(r"<[^>]+>", " ", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", seg, re.S)]
        # 最新の追い切り行を探す: 日付(M/D)を含む位置から
        di = next((j for j, c in enumerate(cells) if re.match(r"^\d{1,2}/\d{1,2}", c)), None)
        last3f = ashiiro = awase = course = baba = None
        if di is not None:
            blk = cells[di: di+16]
            course = blk[1] if len(blk) > 1 else None
            baba = blk[2] if len(blk) > 2 else None
            times = [float(x) for x in blk if re.match(r"^\d{2,3}\.\d$", x)]
            if times: last3f = min(times)           # 締めの3F
            ashiiro = next((x for x in blk if any(w in x for w in ["馬なり", "一杯", "強目", "強め", "余力"])), None)
            awase = next((x for x in blk if ("併" in x or "同入" in x or "先着" in x or "遅れ" in x) and len(x) > 4), None)
        out[ub] = {"name": name, "tanpyo": tanpyo, "arrow": arrow, "last3f": last3f,
                   "ashiiro": ashiiro, "awase": awase, "course": course, "baba": baba}
    return out

POS = ["良化", "上向", "仕上が", "気配良", "手応え十分", "動き良", "絞れ", "意欲的", "余裕", "抜群", "文句なし", "デキ"]
NEG = ["ひと息", "今ひと", "物足り", "手控え", "不満", "重め", "太め", "案外", "ジリ"]

def score(rec):
    sc = 0.0; tags = []
    if "↑" in rec["arrow"]: sc += 2; tags.append("矢印↑")
    if "↓" in rec["arrow"]: sc -= 2; tags.append("矢印↓")
    t3 = rec.get("last3f"); ashi = rec.get("ashiiro") or ""
    if t3 is not None:
        if t3 <= 37.5 and ("馬なり" in ashi or "余力" in ashi): sc += 2.5; tags.append(f"馬なりで好時計(3F{t3})")
        elif t3 <= 37.5: sc += 1.5; tags.append(f"好時計(3F{t3})")
        elif t3 <= 39.0: sc += 0.3; tags.append(f"3F{t3}")
    aw = rec.get("awase") or ""
    if aw:
        if ("先着" in aw) or ("併入" in aw) or ("同入" in aw): sc += 1; tags.append(f"併せ好結果")
        if "遅れ" in aw: sc -= 1; tags.append("併せ遅れ")
    note = (rec.get("tanpyo") or "")
    if any(w in note for w in POS): sc += 1.2; tags.append(f"ポジ短評「{note}」")
    elif any(w in note for w in NEG): sc -= 1.2; tags.append(f"ネガ短評「{note}」")
    elif note: tags.append(f"短評「{note}」")
    return sc, tags

if __name__ == "__main__":
    rid = sys.argv[1]
    d = parse(rid)
    rows = sorted(((score(r)[0], ub, r, score(r)[1]) for ub, r in d.items()), reverse=True)
    print(f"=== {rid} 調教スコア順（{len(rows)}頭） ===")
    for sc, ub, r, tags in rows:
        aw = f" 併[{r['awase'][:20]}]" if r.get("awase") else ""
        print(f"{sc:+.1f} {ub:>2}番 {r['name']:<12} 3F{r.get('last3f')} {r.get('ashiiro') or ''}{aw} | {' / '.join(tags)}")
