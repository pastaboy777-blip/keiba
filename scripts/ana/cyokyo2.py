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
        splits = []
        if di is not None:
            blk = cells[di: di+16]
            course = blk[1] if len(blk) > 1 else None
            baba = blk[2] if len(blk) > 2 else None
            times = [float(x) for x in blk if re.match(r"^\d{2,3}\.\d$", x)]
            # 「last NF」累積(=大きい順に 5F,4F,3F …)。20秒超のみ採用(1Fの端数を除外)
            splits = sorted([t for t in times if t >= 20], reverse=True)
            if times: last3f = min(times)           # 締めの3F
            ashiiro = next((x for x in blk if any(w in x for w in ["馬なり", "一杯", "強目", "強め", "余力"])), None)
            awase = next((x for x in blk if ("併" in x or "同入" in x or "先着" in x or "遅れ" in x) and len(x) > 4), None)
        out[ub] = {"name": name, "tanpyo": tanpyo, "arrow": arrow, "last3f": last3f, "splits": splits,
                   "ashiiro": ashiiro, "awase": awase, "course": course, "baba": baba}
    return out

def accel_lap(rec):
    """加速ラップ判定：last5F/4F/3F の累積からハロン毎ラップを出し、終いに向け加速しているか。
    戻り: (加速フラグ, ラップ列[早→終い], 説明)。データ不足はNone。
    L5=(5F-4F区間), L4=(4F-3F区間), L3avg=3F÷3(締め平均)。単調に速くなる=加速。"""
    s = rec.get("splits") or []
    if len(s) >= 3:                          # T5F, T4F, T3F
        T5, T4, T3 = s[0], s[1], s[2]
        L5, L4, L3 = T5 - T4, T4 - T3, T3 / 3
        laps = [round(L5, 1), round(L4, 1), round(L3, 1)]
        strong = L5 > L4 > L3                 # 完全な右肩上がり加速
        mild = (L4 > L3) and (L5 >= L4 - 0.3) # 終い区間が手前より速い
        if strong: return True, laps, f"加速ラップ(右肩上がり {L5:.1f}→{L4:.1f}→{L3:.1f})"
        if mild:   return True, laps, f"終い加速({L4:.1f}→{L3:.1f})"
        return False, laps, f"減速/平坦({L5:.1f}→{L4:.1f}→{L3:.1f})"
    if len(s) == 2:                          # T4F, T3F のみ
        T4, T3 = s[0], s[1]
        L4, L3 = T4 - T3, T3 / 3
        if L4 > L3 + 0.2: return True, [round(L4,1), round(L3,1)], f"終い加速({L4:.1f}→{L3:.1f})"
        return False, [round(L4,1), round(L3,1)], f"平坦({L4:.1f}→{L3:.1f})"
    return None, s, "ラップ不足(3F単発)"

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
    # 加速ラップ（終いに向け時計が上がる＝次走で上がり最速を出す先行指標。競馬の天才!の"加速ラップ調教"）
    acc, laps, desc = accel_lap(rec)
    if acc is True: sc += 1.5; tags.append(f"★{desc}")
    elif acc is False: tags.append(desc)
    return sc, tags

if __name__ == "__main__":
    rid = sys.argv[1]
    d = parse(rid)
    rows = sorted(((score(r)[0], ub, r, score(r)[1]) for ub, r in d.items()), reverse=True)
    print(f"=== {rid} 調教スコア順（{len(rows)}頭） ===")
    for sc, ub, r, tags in rows:
        aw = f" 併[{r['awase'][:20]}]" if r.get("awase") else ""
        print(f"{sc:+.1f} {ub:>2}番 {r['name']:<12} 3F{r.get('last3f')} {r.get('ashiiro') or ''}{aw} | {' / '.join(tags)}")
