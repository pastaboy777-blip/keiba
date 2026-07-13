"""C型検出エンジン ── 「前で運べる人気薄」を楽天カードから炙り出す。

背景(2026-07 南関8開催の検出検証で確立):
  来た人気薄(5人気以下・3着内)のうち、近3走の厩舎の話(物語A〜H型)で拾えるのは約半分。
  残り半分の主力が「特別な物語は無いが前で楽に運べる中穴」= C型。
  物語(談話)＋C型(脚質)の合算で、来た穴の検出率が 51% → 71% に向上した。

C型スコア:
  ・脚質(前で行ける度) … 逃げ+3 / 先行+2 / 中団0 / 後方-1  (前2走の通過順から推定)
  ・枠 … 内枠(1〜3)で+1 (前有利馬場での先行がスムーズ)
  ・当日バイアス … 前有利日は先行加点を増幅(呼び出し側で weight 指定)
  ・人気薄フィルタ … 5人気以下のみ C型候補とする(妙味を狙う)

依存: 楽天カードのみ(cookie不要・公開データ)。keibabook等の有料データは使わない。
"""
from __future__ import annotations
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
try:
    from scripts.predict_nankan import live_win_odds
except Exception:
    live_win_odds = None

LEG_PTS = {"逃げ": 3.0, "先行": 2.0, "中団": 0.0, "後方": -1.0, "?": 0.0}


def kyaku(recent_runs):
    """前2走の通過順(コーナー先頭からの位置%)で脚質を推定。前走=重み2, 2走前=重み1。"""
    ws = []
    for i, pr in enumerate(recent_runs[:2]):
        cor = getattr(pr, "corner", None) or []
        fs = getattr(pr, "field_size", None)
        if cor and fs and fs > 1:
            ws.append(((cor[0] - 1) / (fs - 1), 2 if i == 0 else 1))
    if not ws:
        return "?"
    a = sum(p * w for p, w in ws) / sum(w for _, w in ws)
    return "逃げ" if a <= 0.15 else "先行" if a <= 0.38 else "中団" if a <= 0.62 else "後方"


def cgata_score(lab, waku, ninki, zen_yuri=True):
    """C型スコアと候補フラグ。人気薄(5人気以下)×前で行ける、を穴候補★とする。"""
    s = LEG_PTS.get(lab, 0.0)
    if waku and waku <= 3:
        s += 1.0
    if zen_yuri and lab in ("逃げ", "先行"):
        s += 1.0  # 前有利日は先行を増幅
    tag = ""
    is_ana = (ninki is None or ninki >= 5) and lab in ("逃げ", "先行")
    if is_ana:
        tag = "C" + lab + ("×内" if (waku and waku <= 3) else "")
    return round(s, 1), is_ana, tag


def _wt(s):
    """馬体重文字列(例 '462+2' や '462') から体重(kg)を取り出す。"""
    import re
    m = re.search(r"(\d{3})", str(s))
    return int(m.group(1)) if m else None


def weight_trend(recent_runs, n=5, thr=4):
    """近n走の馬体重トレンド。5走前(古)→前走(新)の差。
    戻り値: (diff, label, weights)。label = '増'(>=+thr) / '減'(<=-thr) / '横'。
    南関の経験則: 5走前から体重が増えている馬は人気薄で穴をあけやすい(第4の検出層)。
    """
    ws = [_wt(getattr(pr, "horse_weight", None)) for pr in recent_runs[:n]]
    ws = [w for w in ws if w]
    if len(ws) < 2:
        return None, "?", ws
    d = ws[0] - ws[-1]  # 前走(新) - 5走前(古)
    lab = "増" if d >= thr else "減" if d <= -thr else "横"
    return d, lab, ws


def _get_retry(cli, url, n=4):
    for i in range(n):
        try:
            return cli.get(url)
        except Exception:
            if i == n - 1:
                raise
            time.sleep(2 * (i + 1))


def detect(place, ymd, zen_yuri=True):
    """指定開催の全レースについて C型穴候補を返す。
    戻り値: {race_no: [ {umaban, name, jockey, waku, lab, ninki, score, cgata, tag}, ... ]}
    """
    cli = PoliteClient()
    idx = _get_retry(cli, "https://keiba.rakuten.co.jp/race_card/list/RACEID/" + day_index_race_id(ymd, place))
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[place]))
    out = {}
    for r, rid in races.items():
        try:
            card = P.parse_card_page(_get_retry(cli, "https://keiba.rakuten.co.jp/race_card/list/RACEID/" + rid), rid)
        except Exception:
            out[r] = []
            continue
        od = live_win_odds(cli, rid) if live_win_odds else {}
        rows = []
        for e in card.entries:
            if e.umaban is None:
                continue
            lab = kyaku(e.recent_runs)
            waku = getattr(e, "waku", None)
            ninki = (od.get(e.umaban) or {}).get("pop") if od else None
            sc, is_ana, tag = cgata_score(lab, waku, ninki, zen_yuri)
            wd, wlab, ws = weight_trend(e.recent_runs)
            # 第4層: 前で行けず物語も無いが「体重増」の人気薄=見えない穴の受け皿
            weight_ana = wlab == "増" and (ninki is None or ninki >= 5)
            rows.append(dict(umaban=e.umaban, name=e.horse_name, jockey=e.jockey or "",
                             waku=waku, lab=lab, ninki=ninki, score=sc, cgata=is_ana, tag=tag,
                             wt_diff=wd, wt_label=wlab, wt_ana=weight_ana))
        rows.sort(key=lambda x: -x["score"])
        out[r] = rows
    return out


if __name__ == "__main__":
    place = sys.argv[1] if len(sys.argv) > 1 else "浦和"
    ymd = sys.argv[2] if len(sys.argv) > 2 else "20260714"
    res = detect(place, ymd)
    for r in sorted(res):
        ana = [x for x in res[r] if x["cgata"]]
        if not ana:
            continue
        print(f"\n=== {place} {r}R C型穴候補 ===")
        for x in ana:
            pop = f"{x['ninki']}人" if x["ninki"] else "?人"
            print(f"  {x['umaban']:>2} {x['name']} {x['jockey'][:4]} {pop} 枠{x['waku']} {x['lab']} [{x['tag']}] C={x['score']}")
