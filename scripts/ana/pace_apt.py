"""南関版ペース適性（TARGET指数のS/H/F/Uを南関で機能する形に）。
純粋なS/H標本は南関で薄い→過去の"好走(3着内)"を【通過位置×ペース】で分類してタグ化。
 ・持続H型 : ハイ/締まった流れで前〜好位のまま好走した実績アリ＝流れても止まらない
 ・瞬発S型 : 後方から差して好走した実績が主＝速い脚頼み(遅い流れ向き)
 ・自在F   : 前でも後ろでも好走
 ・楽逃げ依存: スロー楽逃げでしか好走なし＝ハイで危険
 ・不明U   : 好走標本なし
今日の想定ペース(逃げ頭数→ハイ/ミドル/スロー)と適性を突き合わせ、"噛み合う馬/危険な馬"を出す。
"""
import re, os, sys
import hidden as H

def apt(cd, nrecent=10):
    rs = H.parse_db_races(cd)[:nrecent]
    nf = nc = nh = ns_easy = ngood = 0
    for (y, mo, d, baba, dist, pace, ag, c1, ch, nk) in rs:
        if ch is None: continue
        good = ch <= 3
        if good:
            ngood += 1
            if c1 is not None and c1 <= 4: nf += 1          # 前〜好位で好走
            if c1 is not None and c1 >= 7: nc += 1          # 後方から差して好走
            if pace in ("H",): nh += 1                       # ハイで好走
            if pace == "S" and c1 is not None and c1 <= 2: ns_easy += 1
    if ngood == 0:
        return {"tag": "U不明", "kind": "U", "note": "好走標本なし", "n": 0}
    if nh >= 1 and nf >= 1:
        return {"tag": "H持続", "kind": "H", "note": f"ハイ/前で好走{nh}回", "n": ngood}
    if nc >= 2 and nh == 0:
        return {"tag": "S瞬発", "kind": "S", "note": f"後方差し好走{nc}回", "n": ngood}
    if nf >= 1 and nc >= 1:
        return {"tag": "F自在", "kind": "F", "note": "前後どちらでも好走", "n": ngood}
    if ns_easy >= 1 and nh == 0:
        return {"tag": "楽逃げ依存", "kind": "S!", "note": "スロー楽逃げ限定＝ハイ危険", "n": ngood}
    # 位置準拠フォールバック
    return ({"tag": "前型", "kind": "F", "note": "前で好走傾向", "n": ngood} if nf >= nc
            else {"tag": "差型", "kind": "S", "note": "差して好走傾向", "n": ngood})

def match(kind, pace_today):
    """今日の想定ペース(ハイ/ミドル/スロー)と適性kindの噛み合い。→ (◎○△▲✖, 一言)"""
    hi = "ハイ" in pace_today or "超ハイ" in pace_today
    slow = "スロー" in pace_today or "ドスロー" in pace_today
    if hi:
        if kind == "H": return "◎", "ハイ歓迎(持続)"
        if kind in ("S", "F"): return "○", "前崩れを差せる"
        if kind == "S!": return "✖", "ハイで楽逃げ不発＝危険"
    if slow:
        if kind in ("F", "H", "S!"): return "◎", "前残りに乗れる"
        if kind == "S": return "▲", "スロー瞬発は届きにくい"
    # ミドル
    if kind in ("F", "H"): return "○", "流れ不問"
    if kind == "S": return "△", "展開待ち"
    return "-", ""

if __name__ == "__main__":
    import glob, monogatari as M
    if len(sys.argv) >= 2:
        print(cd := sys.argv[1], apt(sys.argv[1]))
    else:
        for f in glob.glob(os.path.join(M.ARC, "umaNEW_*.html"))[:12]:
            cd = os.path.basename(f)[7:-5]
            print(f"{cd}: {apt(cd)}")
