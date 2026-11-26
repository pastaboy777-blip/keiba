"""気配(追い切り)スコア ── 南関の"追い切り好転"を全頭スコア化。
【南関の現実】競馬ブックの調教時計は1レース1頭しか非公表 → 追い切りの気配は
主に「厩舎談話」の言葉で全頭に出る。よって3ソースを統合する:
  A) 談話(全頭) … 追い切り/気配の言葉を拾う ("動き上々""終い伸びた""気配上向き"等)
  B) 調教時計(掲載1頭) … 末1F時計×脚色で加点
  C) 出馬表(全頭) … ブリンカー新装着=気性改善の穴サイン
穴サイン: 人気薄(単勝下位) かつ 気配スコア>=2 → ★気配好転の穴候補
標準ライブラリ + curl(kb.conf) + monogatari(_get/race_danwa) + cyokyo_ana。
"""
import re, os, sys
import monogatari as M
import cyokyo_ana as C

# 談話の追い切り/気配ワード
KEHAI_POS = ["動き上々", "動きは上々", "動きが良", "動き良", "終いよく", "終いは良", "終い伸び", "終いの伸び",
             "反応良", "反応が良", "気配は上向", "気配が上向", "気配も上向", "上向いてき", "状態は上向",
             "状態が上向", "デキはいい", "デキは良", "デキが良", "デキ上向", "仕上がりは良", "仕上がり上々",
             "絞れ", "馬体良化", "良化", "上積み", "変わり身", "格段", "一変", "渋太", "しっかりしてき",
             "力強", "抜群", "文句なし", "好調キープ", "好調", "動ける", "躍動"]
KEHAI_NEG = ["追い切り手控え", "手控え", "ひと息", "一息", "太め", "余裕があり", "余裕残", "使ってから",
             "叩いてから", "ひと叩きして", "案外", "物足り", "地味", "重目", "息遣いがひと息",
             "息遣いはひと息", "まだこれから", "本来のデキには", "見劣", "頼りな", "デキ落ち"]

def blinker_new(rid):
    """出馬表からブリンカー新装着(=気性改善)の馬番集合。"""
    o = os.path.join(M.ARC, f"syu_{rid}.html")
    M._get(f"{M.BASE}/chihou/syutuba/{rid}", o)
    h = open(o, encoding="utf-8", errors="replace").read()
    out = set()
    for m in re.finditer(r'<td class="umaban">(\d+)</td>(.{0,400}?)</tr>', h, re.S):
        ub = int(m.group(1)); seg = m.group(2)
        # ブリンカー列に「B」等の装着マーク、特に"blinker"クラスや"新"
        if re.search(r'(blinker|ブリンカー)[^<]*[B新装]', seg) or ('新' in seg and 'ブリンカー' in seg):
            out.add(ub)
    return out

def danwa_kehai(comment):
    sc = 0.0; tags = []
    if not comment: return sc, tags
    posn = sum(1 for w in KEHAI_POS if w in comment)
    negn = sum(1 for w in KEHAI_NEG if w in comment)
    if posn: sc += min(2.0, 1.0 + 0.5 * posn); tags.append(f"談話気配+({posn})")
    if negn: sc -= min(2.0, 1.0 * negn); tags.append(f"談話気配-({negn})")
    return sc, tags

def analyze(rid, unpop_from=6):
    danwa = M.race_danwa(rid)                    # {umacd:{umaban,name,comment}}
    od, rank = C.odds_rank(rid)
    clock = C.parse(rid)                          # {umaban:{arrow,soukan,last}} (掲載1頭)
    try: blk = blinker_new(rid)
    except Exception: blk = set()
    rows = []
    for cd, info in danwa.items():
        ub = info.get("umaban")
        if ub is None: continue
        sc, tags = danwa_kehai(info.get("comment", ""))
        # 調教時計ボーナス(掲載馬のみ)
        if ub in clock:
            cs, ct = C.score(clock[ub])
            if cs:
                sc += cs; tags += [f"調教:{t}" for t in ct]
        # ブリンカー新装着
        if ub in blk:
            sc += 1.5; tags.append("ブリンカー新装着")
        pk = rank.get(ub, 99)
        ana = "★気配好転の穴" if (pk >= unpop_from and sc >= 2) else ""
        rows.append((sc, ub, info.get("name"), pk, od.get(ub), tags, ana))
    rows.sort(key=lambda x: (-x[0], x[3]))
    return rows

if __name__ == "__main__":
    rid = sys.argv[1]
    print(f"=== 気配(追い切り)スコア {rid} ===")
    for sc, ub, nm, pk, o, tags, ana in analyze(rid):
        star = "  " + ana if ana else ""
        print(f"  {sc:+.1f} | {ub:2}番 {nm} | {pk}人{o} | {'/'.join(tags)}{star}")
