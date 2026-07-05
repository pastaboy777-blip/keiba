"""楽天競馬の出馬表から、南関の1レースを『走らせる』観点で予想する。

出馬表(各馬の前5走)→ core.features.horse_score で総合強さスコアを算出し、
Plackett-Luce で 上位3着確率 / 三連複・三連単確率に変換する。
想定馬場(--baba)を指定すると baba_fit(馬場適性)が効き、道悪巧者を評価できる。

オッズが開いていない先のレースでも予想できる(その場合は期待値ではなく
モデル確率での推奨。オッズ確定後は build_dataset/backtest 系で回収率検証へ)。

実行例:
    python3 scripts/predict_nankan.py --date 2026-06-04 --place 船橋 --race 11 --baba 不
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nankeiba.scraping.race_id import day_index_race_id, NANKAN_CODES, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P
from nankeiba.scraping import enrich as E
from nankeiba.core import features as F
from nankeiba.core import probability as pb

CARD_URL = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{race_id}"
RESULT_URL = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{race_id}"
ODDS_URL = "https://keiba.rakuten.co.jp/odds/tanfuku/RACEID/{race_id}"
BABA_FULL = {"良": "良", "稍": "稍重", "重": "重", "不": "不良"}


def live_win_odds(client, race_id):
    """楽天のオッズ(単複)ページから確定ライブオッズを取る(netkeiba地方はProxyで403のため)。
    戻り値: {馬番: {"win": 単勝float, "pop": 人気int, "place": "複勝下-上", "weight": 連対時馬体重}}。
    出馬表段階のexp_oddsは想定値でズレるため、確定値はこちらを使う。
    """
    import re as _re
    from bs4 import BeautifulSoup as _BS
    out = {}
    try:
        html = client.get(ODDS_URL.format(race_id=race_id))
    except Exception:  # noqa: BLE001
        return out
    soup = _BS(html, "html.parser")
    for t in soup.find_all("table"):
        heads = [th.get_text(strip=True) for th in t.find_all("th")]
        if "単勝オッズ" not in heads or "人気" not in heads:
            continue
        for tr in t.find_all("tr")[1:]:
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(tds) < 11:
                continue
            mnum = _re.match(r"\d+", tds[0])
            if not mnum:
                continue
            um = int(mnum.group())
            try:
                win = float(tds[7])
            except ValueError:
                win = None
            pm = _re.search(r"(\d+)番人気", tds[9])
            out[um] = {"win": win, "pop": int(pm.group(1)) if pm else None,
                       "place": tds[8].replace(" ", ""), "weight": tds[5]}
        break
    return out


def _t2s(t):
    if not t or ":" not in str(t):
        return None
    m, s = str(t).split(":")
    return int(m) * 60 + float(s)


def day_target_time(client, races, distance):
    """当日の決着時計トレンドから、この距離の『想定勝ち時計(秒)』を逆算する。

    同距離の確定レースがあればその中央値、無ければ全確定レースの秒/1000m中央値×距離。
    返り値: (想定秒, 説明) / 確定レースが無ければ (None, ...)。
    """
    same, idx = [], []
    for _rno, rid in races:
        try:
            res = P.parse_result_page(client.get(RESULT_URL.format(race_id=rid)), rid)
        except Exception:  # noqa: BLE001
            continue
        if not res.rows:
            continue
        sec = _t2s(res.rows[0].time)
        if not sec:
            continue
        if res.distance == distance:
            same.append(sec)
        idx.append(sec / res.distance * 1000)
    import statistics as st
    if same:
        return st.median(same), f"同距離{len(same)}R中央値"
    if idx:
        return st.median(idx) * distance / 1000, f"全{len(idx)}R秒/1000m換算"
    return None, "確定レースなし"


def weights_for(mode: str) -> F.ScoreWeights:
    """予想モード別の重み。

    shomousen(消耗戦/時計のかかる馬場): 6/3 1R・2R の学びを反映。
    決着時計が遅い消耗戦では、ズブさ(タフネス)と短間隔(連闘・叩き上がり)で
    使い込まれた馬が浮上し、使い込み疲労のマイナスは出にくい。道悪適性も加点。
    """
    w = F.ScoreWeights()
    if mode == "shomousen":
        w.toughness = 0.9      # 0.3 → 大幅加点(ズブさ=最重要)
        w.interval_fit = 0.9   # 0.6 → 短間隔有利を強調
        w.tatakii = 1.3        # 1.0 → 叩き上がり
        w.baba_fit = 0.8       # 0.5 → 道悪適性
        w.senkou = 0.9         # 0.5 → 前で運べる馬を大幅加点(上がり使えない=前残り)
        w.agari = 0.0          # 0.3 → 切れ味は無効(上がりが使えない馬場)
        w.fatigue = 0.4        # 1.0 → 使い込みのマイナスを軽減
    elif mode == "zenzan":
        # 前残り/上がり使えない馬場の"中庸"版: 地力(ability)は残したまま、
        # 前で運べる脚質と道悪適性だけ上乗せ、切れ味は無効。堅い決着を壊さない。
        w.senkou = 0.9         # 前で運べる馬を加点
        w.agari = 0.0          # 切れ味は無効
        w.baba_fit = 0.7       # 道悪適性
    return w


def class_to_bias(race_class) -> str:
    """クラスから脚質バイアスを判定。C1以上(/B/A/オープン)=前、C2/C3/3歳=差し。

    (6/11大井の検証: 上級条件ほど前残り、下級は差しが決まる傾向)
    """
    if not race_class:
        return "front"
    rc = race_class
    if ("オープン" in rc or "ＯＰ" in rc or "Ｃ１" in rc or "C1" in rc
            or re.search(r"[ＡＢAB][０-９0-9]", rc)):
        return "front"        # 上級条件=前残り傾向
    return "sashi"            # Ｃ２/Ｃ３/3歳など下級=差し


def agari_style_adjust(card, *, scale: float = 0.35):
    """上がりが使えない(前残り)馬場向けの脚質補正。

    各馬の近走の上がり(中央値)をレース内で比較し、**遅い=持続/前型を加点**、
    **速い=切れ味/差し型を割引**する。上がりが使えない馬場では切れる脚は不発で、
    前で粘れる持続型が残るため。返り値: {馬番: 補正スコア(±scale程度)}。
    """
    med = {}
    for e in card.entries:
        if e.umaban is None:
            continue
        vals = [pr.agari for pr in e.recent_runs if pr.agari]
        if vals:
            med[e.umaban] = _median(vals)
    if len(med) < 3:
        return {}
    order = sorted(med, key=lambda um: -med[um])   # 遅い順
    n = len(order)
    return {um: scale * (1 - 2 * i / (n - 1)) for i, um in enumerate(order)}


def jockey_top3_from_samples(paths) -> dict:
    """蓄積データから騎手の3着内率(%)を推定。

    出馬表に騎手成績が未反映(発走直前まで0%)の時のフォールバックに使う。
    返り値: {騎手名: 3着内率%}(全体平均へ縮約)。
    """
    starts: dict[str, int] = {}
    hits: dict[str, int] = {}
    tot_s = tot_h = 0
    for p in paths:
        if not Path(p).exists():
            continue
        for line in open(p, encoding="utf-8"):
            rec = json.loads(line)
            for h in rec["horses"]:
                j, fp = h.get("jockey"), h.get("finish_pos")
                if not j or fp is None:
                    continue
                starts[j] = starts.get(j, 0) + 1
                hits[j] = hits.get(j, 0) + (1 if fp <= 3 else 0)
                tot_s += 1
                tot_h += 1 if fp <= 3 else 0
    if tot_s == 0:
        return {}
    prior = tot_h / tot_s
    pseudo = 15.0
    return {j: 100.0 * (hits[j] + pseudo * prior) / (starts[j] + pseudo) for j in starts}


def trainer_stats_from_samples(paths) -> F.ConnStats:
    """蓄積済み充実データから調教師の好走率(3着内率)を推定。"""
    starts: dict[str, int] = {}
    hits: dict[str, int] = {}
    tot_s = tot_h = 0
    for p in paths:
        if not Path(p).exists():
            continue
        for line in open(p, encoding="utf-8"):
            rec = json.loads(line)
            fs = rec.get("field_size") or 0
            for h in rec["horses"]:
                t = h.get("trainer")
                fp = h.get("finish_pos")
                if not t or fp is None:
                    continue
                hit = 1 if fp <= 3 else 0
                starts[t] = starts.get(t, 0) + 1
                hits[t] = hits.get(t, 0) + hit
                tot_s += 1
                tot_h += hit
    if tot_s == 0:
        return F.ConnStats()
    prior = tot_h / tot_s
    pseudo = 10.0
    rates = {t: (hits[t] + pseudo * prior) / (starts[t] + pseudo) for t in starts}
    return F.ConnStats(rates=rates, default=prior)


def wet_ana_stats_from_samples(paths, *, pop_min: int = 6) -> dict:
    """道悪(重/不良)×人気薄に絞った『厩舎・種牡馬の穴 3着内率』を推定する。

    重馬場では『道悪巧者の厩舎』と『ダート/道悪適性の種牡馬』が人気薄でも
    3着内に粘る傾向が強い(川崎120Rの集計でベース約11%に対し2〜4倍)。
    各率は全体ベース(prior)へベイズ縮約し、小標本のブレを抑える。

    返り値: {"base": ベース3着内率, "trainer": {名:率}, "sire": {名:率}}
    pop_min 番人気以下のみを母集団とする(=穴の定義)。
    """
    t_s: dict[str, int] = {}
    t_h: dict[str, int] = {}
    s_s: dict[str, int] = {}
    s_h: dict[str, int] = {}
    tot_s = tot_h = 0
    for p in paths:
        if not Path(p).exists():
            continue
        for line in open(p, encoding="utf-8"):
            rec = json.loads(line)
            baba = (rec.get("baba") or "")[:1]
            if baba not in ("重", "不"):
                continue
            for h in rec["horses"]:
                fp, pop = h.get("finish_pos"), h.get("exp_pop")
                if fp is None or pop is None or pop < pop_min:
                    continue
                hit = 1 if fp <= 3 else 0
                tot_s += 1
                tot_h += hit
                tr = h.get("trainer")
                if tr:
                    t_s[tr] = t_s.get(tr, 0) + 1
                    t_h[tr] = t_h.get(tr, 0) + hit
                si = h.get("sire")
                if si:
                    s_s[si] = s_s.get(si, 0) + 1
                    s_h[si] = s_h.get(si, 0) + hit
    if tot_s == 0:
        return {"base": 0.0, "trainer": {}, "sire": {}}
    base = tot_h / tot_s
    tr_rates = {t: (t_h[t] + 12.0 * base) / (t_s[t] + 12.0) for t in t_s}
    si_rates = {s: (s_h[s] + 8.0 * base) / (s_s[s] + 8.0) for s in s_s}
    return {"base": base, "trainer": tr_rates, "sire": si_rates}


# ズブ穴ランキングの再重み付け(improve_zubu.py で検証=本線3着内 12.8%→21.5%)。
# 人気薄の3着内を両期間で安定して予測できた信号だけを符号つき重みで線形結合する。
# 値は標準化(蓄積データの平均/標準偏差)してから掛ける。市場情報(人気)は妙味を
# 損なうため既定では使わない(=技能型)。
# 重みは learn_zubu.py のロジスティック回帰で学習した係数(標準化後)に準拠。
# jockey(騎手の質)と ability(地力)が二大ドライバー、senkou/agari は僅少。
ZUBU_V2_WEIGHTS = {"jockey": 0.38, "ability": 0.29, "senkou": 0.02, "agari": -0.02}
# 高知ファイナル専用(learn_zubu_kochi.pyで再学習)。地力(ability)がほぼ無効化し騎手が
# 支配的、senkouは前寄りに僅増、agariは差し寄り。検証(リーク無)で本線3着内 16.0%→20.0%。
# 「実績を捨て、騎手で買う」型。ファイナル(最終R)でのみ使う。
ZUBU_V2_WEIGHTS_KOCHI_FINAL = {"jockey": 0.43, "ability": -0.01, "senkou": 0.12, "agari": -0.06}


def zubu_v2_stats_from_samples(paths, *, pop_min: int = 6) -> dict:
    """v2スコアの標準化統計(人気薄での jockey/ability/senkou/agari の平均・標準偏差)。"""
    acc: dict[str, list[float]] = {k: [] for k in ("jockey", "ability", "senkou", "agari")}
    for p in paths:
        if not Path(p).exists():
            continue
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            for h in rec["horses"]:
                pop = h.get("exp_pop")
                if pop is None or pop < pop_min:
                    continue
                feats = h.get("features") or {}
                vals = [x["agari"] for x in h.get("recent_runs", []) if x.get("agari")]
                if h.get("jockey_top3_rate") is not None:
                    acc["jockey"].append(h["jockey_top3_rate"])
                if feats.get("ability") is not None:
                    acc["ability"].append(feats["ability"])
                acc["senkou"].append(_senkou_from_recent(h.get("recent_runs", [])))
                if vals:
                    acc["agari"].append(sum(vals) / len(vals))
    stats = {}
    for k, xs in acc.items():
        if not xs:
            stats[k] = (0.0, 1.0)
            continue
        m = sum(xs) / len(xs)
        sd = (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5 or 1.0
        stats[k] = (m, sd)
    return stats


def _senkou_from_recent(recent) -> float:
    """近走のコーナー通過順から先行力(senkou)を算出(JSONL用の簡易版)。"""
    recs = []
    for r in recent:
        if r.get("field_size") and r.get("corner"):
            recs.append(F.iv.RunRecord(
                date=r.get("date") or "2000-01-01", place=r.get("place") or "?",
                distance=r.get("distance") or 0, field_size=r["field_size"],
                finish_pos=r.get("finish_pos") or 1, corner_pos=r.get("corner") or []))
    return F.senkou_power(recs) if recs else 0.0


def zubu_v2_score(jockey_rate, ability, senkou, agari_med, stats, weights=None) -> float:
    """検証済みの線形スコア(標準化×符号つき重み)。値が大きいほど3着内に来やすい。

    weights を渡すと重みを差し替えられる(例: 騎手ファクターを外す)。
    """
    vals = {"jockey": jockey_rate, "ability": ability, "senkou": senkou, "agari": agari_med}
    s = 0.0
    for k, w in (weights or ZUBU_V2_WEIGHTS).items():
        v = vals.get(k)
        if v is None:
            continue
        m, sd = stats.get(k, (0.0, 1.0))
        s += w * (v - m) / sd
    return s


def mark(rank: int) -> str:
    return {1: "◎", 2: "○", 3: "▲", 4: "△", 5: "△"}.get(rank, " ")


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if n == 0 else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)


def _pstd(xs):
    """母標準偏差(2点未満は None)。"""
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def _best_time_at(entry, distance):
    """この距離での自己最速タイム(秒)。無ければ None。"""
    ts = [_t2s(pr.time) for pr in entry.recent_runs if pr.distance == distance and _t2s(pr.time)]
    return min(ts) if ts else None


def time_fit(entry, distance, target_time, *, margin: float = 0.8):
    """タイム適性: 当日想定勝ち時計に対し『今日の決着に間に合う持ち時計か』。

    時計は"足切り＋小さな加点"として使う(最速=勝ちではないので過大評価しない)。
    margin を広げると『際どい』判定の幅が広がり、足切り(fail)が緩む。
    返り値: (flag, bonus, tag) ── flag 'fail' は足切り対象。
    """
    if target_time is None:
        return "na", 0.0, None
    best = _best_time_at(entry, distance)
    if best is None:
        return "na", 0.0, None        # 当該距離の持ち時計なし=判定不能(切らない)
    if best <= target_time:
        return "ok", 1.0, f"時計足りる(自己最速{best:.1f}≦想定{target_time:.1f})"
    if best <= target_time + margin:
        return "edge", 0.5, f"時計際どい({best:.1f})"
    return "fail", 0.0, f"時計不足({best:.1f}>想定{target_time:.1f})"


def zubu_ana_picks(card, jockeys, *, pop_min: int = 6, target_time=None,
                   jockey_rates=None, jockey_div: float = 12.0, bias: str = "front",
                   stab: bool = False, baba: str | None = None, wet_stats=None,
                   v2_stats=None, v2_weights=None, use_jockey: bool = True,
                   time_margin: float = 0.8, keep_slow: bool = False):
    """『ズブい馬を走らせる』観点 ＋ タイム適性フィルターで人気薄(穴)を拾う。

    方針:
      - タイム適性: 当日想定勝ち時計に間に合わない馬は足切り、間に合う馬に小加点
        (着順は無視。"着順は悪いが時計は足りている"人気薄を救うのが狙い)
      - 上がりの遅い馬を重視(切れ味より前粘り・持続型=ズブさ)
      - 乗り替わり(特に上位騎手への強化)
      - 出走間隔: 連闘/中1〜2週で詰めてきた or 適度な間隔
      - 場替わり・距離短縮(条件を合わせてきた=走らせにきた)
    """
    # レース内の上がり順位(遅い=高ポイント)
    ag = {}
    for e in card.entries:
        vals = [pr.agari for pr in e.recent_runs if pr.agari]
        ag[e.umaban] = _median(vals)
    have = sorted([(um, a) for um, a in ag.items() if a is not None], key=lambda x: -x[1])
    n = len(have)
    slow_pts = {}
    for i, (um, _a) in enumerate(have):
        pct = i / (n - 1) if n > 1 else 0.0   # 0=最も遅い
        slow_pts[um] = 2.0 if pct <= 0.3 else (1.0 if pct <= 0.5 else 0.0)

    picks = []
    for e in card.entries:
        if e.umaban is None:
            continue   # 馬番が取れない行はスキップ
        if e.exp_pop is not None and e.exp_pop < pop_min:
            continue   # 人気サイドは穴ピックの対象外
        records = E.past_runs_to_records(e)
        sig = E.running_signals(e, F.RaceContext(
            date=card.date, place=card.place, distance=card.distance,
            field_size=card.field_size, jockey=e.jockey, trainer=e.trainer),
            records)
        tf_flag, tf_bonus, tf_tag = time_fit(e, card.distance, target_time,
                                             margin=time_margin)
        if tf_flag == "fail" and not keep_slow:
            continue   # 当日の決着に間に合わない=足切り(keep_slow で除外せず減点)
        score = tf_bonus
        tags = [tf_tag] if tf_tag else []
        if tf_flag == "fail":          # keep_slow 時: 残すが減点(時計不足の保険)
            score -= 0.5
        sp = slow_pts.get(e.umaban, 0.0)
        if sp:
            score += sp
            tags.append("上がり遅い(持続型)" if sp >= 2 else "上がりやや遅")
        d = sig["days_since_last"]
        if d is not None and d <= 14:
            score += 1.0
            tags.append(f"連闘/詰め({d}日)")
        elif d is not None and 15 <= d <= 20:
            score += 1.5
            tags.append(f"中1-2週({d}日)")
        elif d is not None and d >= 35:
            score += 1.0
            tags.append(f"間隔あけ({d}日)")
        if sig["jockey_changed"]:
            up = jockeys.get(e.jockey) - jockeys.get(sig["prev_jockey"])
            if up > 0.01:
                score += 1.5
                tags.append(f"乗替強化→{e.jockey}")
            else:
                score += 0.5
                tags.append(f"乗替→{e.jockey}")
        if sig["place_changed"]:
            score += 0.5
            tags.append("場替わり")
        if sig["distance_change"] is not None and sig["distance_change"] < 0:
            score += 0.5
            tags.append(f"距離短縮({sig['distance_change']}m)")
        # 脚質ファクター。bias=front(既定)は前で運べる馬を加点(前残り馬場)、
        # bias=sashi はトラックバイアスが差し有利の時間帯用に後方/差し脚を加点。
        sen = F.senkou_power(records)
        if bias == "sashi":
            if sen <= -0.2:
                score += -sen * 2.5
                tags.append(f"差し脚(後方{sen:+.2f})")
            elif sen >= 0.15:
                score += -sen * 1.5          # 前付けは減点(差し有利の時間帯)
        else:  # front
            if sen >= 0.2:
                score += sen * 2.5
                tags.append(f"前で運べる(脚質{sen:+.2f})")
            elif sen <= -0.15:
                score += sen * 1.5           # 後方型は減点(人気薄で-1.4)
        # 純持続/スタミナ型: 「その距離にしては上がりが遅い」走が近5走にある馬。
        # (1600mの41秒は普通なので絶対値ではなく距離相対で判定)。
        # 切れ味皆無の前粘り型=時計のかかる消耗戦の馬場で穴になる。
        def _slow_for_dist(pr):
            if not pr.distance or not pr.agari:
                return False
            norm = 37.5 + pr.distance / 1000 * 2.0   # 距離別の上がり3F目安(実態準拠)
            return pr.agari >= norm + 1.2            # 目安より1.2秒以上遅い=純持続
        if any(_slow_for_dist(pr) for pr in e.recent_runs):
            score += 1.0
            tags.append("純持続型(距離比・上がり遅)")
        # 上がり安定(--stab): 毎回ほぼ同じ上がりを刻む=ムラがない人気薄。
        # 単体では重/不・人気薄 +2.1 だが、複合に足すと精度低下(15.1→13.8)のため既定オフ。
        if stab:
            agaris = [pr.agari for pr in e.recent_runs if pr.agari]
            sd = _pstd(agaris) if len(agaris) >= 3 else None
            if sd is not None and sd <= 0.6:
                score += 1.0
                tags.append(f"上がり安定(毎回同じ・std{sd:.2f})")
        # ★主軸: 騎手の質(上位騎手が人気薄に乗る=市場が過小評価)。3ヶ月検証で
        #   人気薄3着内率+12.7%、トップピック的中12.0%→16.4%(/6重み)に改善。
        jq = e.jockey_top3_rate or 0.0
        if jq <= 0 and jockey_rates:          # カード未反映時は蓄積データで代替
            jq = jockey_rates.get(e.jockey, 0.0)
        if use_jockey and jq > 0:
            score += jq / jockey_div          # 重みは --jw で調整(大=弱める)
            if jq >= 25:
                tags.insert(0, f"上位騎手({e.jockey}・3着内{jq:.0f}%)")
        # ★重馬場(道悪)限定の穴特徴量: 厩舎の道悪穴率 + ダート/道悪巧者の種牡馬。
        #   蓄積データ(道悪×人気薄)で平均より上振れする厩舎・血統を加点する。
        if wet_stats and baba in ("重", "不") and wet_stats.get("base"):
            base = wet_stats["base"]
            tr = wet_stats["trainer"].get(e.trainer)
            if tr and tr / base > 1.05:
                b = min(1.2, (tr / base - 1.0) * 1.5)
                score += b
                tags.append(f"道悪穴厩舎({e.trainer}・{tr*100:.0f}%/{base*100:.0f}%)")
            si = wet_stats["sire"].get(e.sire)
            if si and si / base > 1.05:
                b = min(1.2, (si / base - 1.0) * 1.5)
                score += b
                tags.append(f"道悪巧者血統({e.sire})")
        # ★v2ランキング(既定): 検証で安定して効く信号だけの線形スコアで並べ替える。
        #   現行ヒューリスティックの穴度は3着内をほぼ判別できなかった(相関≒0)ため、
        #   表示順は v2 を主、ヒューリスティック score は補助(足切り/タグ生成)に使う。
        if v2_stats is not None:
            ability = F.horse_features(records, F.RaceContext(
                date=card.date, place=card.place, distance=card.distance,
                field_size=card.field_size, jockey=e.jockey, trainer=e.trainer,
                baba=baba)).get("ability")
            agari_med = _median([pr.agari for pr in e.recent_runs if pr.agari])
            jq2 = e.jockey_top3_rate or (jockey_rates or {}).get(e.jockey, 0.0)
            rank_key = zubu_v2_score(jq2, ability, F.senkou_power(records),
                                     agari_med, v2_stats, weights=v2_weights)
            picks.append((e, rank_key, tags))
        elif score > 0:
            picks.append((e, score, tags))
    picks.sort(key=lambda x: -x[1])
    return picks


def main() -> None:
    ap = argparse.ArgumentParser(description="楽天競馬 南関 1レース予想(走らせる観点)")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--place", choices=list(ALL_CODES), required=True)
    ap.add_argument("--race", type=int, required=True)
    ap.add_argument("--baba", choices=list(BABA_FULL), default="良", help="想定馬場 良/稍/重/不")
    ap.add_argument("--mode", choices=["normal", "shomousen", "zenzan"], default="normal",
                    help="shomousen=消耗戦/時計のかかる馬場(タフネス・短間隔を加点)")
    ap.add_argument("--temp", type=float, default=1.0, help="確率の尖り(小さいほど自信)")
    ap.add_argument("--ana", action="store_true",
                    help="ズブ穴ピックアップ(タイム適性フィルター＋上がり遅さ・乗替・間隔詰めで人気薄を拾う)")
    ap.add_argument("--target-time", type=float, default=None,
                    help="想定勝ち時計[秒](未指定なら当日トレンドから自動逆算)")
    ap.add_argument("--jw", type=float, default=12.0,
                    help="騎手の質の弱め係数(大きいほど騎手ファクターを下げる。既定12)")
    ap.add_argument("--pop-min", type=int, default=6,
                    help="ズブ穴の人気しきい値(この人気以下が対象。既定6=6番人気以下)")
    ap.add_argument("--bias", choices=["front", "sashi", "auto"], default="front",
                    help="脚質バイアス: front/sashi/auto(クラスで自動:C1以上=前,下級=差し)")
    ap.add_argument("--stab", action="store_true",
                    help="上がり安定(毎回同じ上がり)を加点。単体+2.1だが複合では精度低下のため任意")
    ap.add_argument("--wet-ana", action="store_true",
                    help="重馬場の穴特徴量(厩舎道悪穴率+血統)を有効化。"
                         "1210Rのバックテストでエッジ無しと判明したため既定OFF(実験用)")
    ap.add_argument("--legacy-ana", action="store_true",
                    help="ズブ穴ランキングを旧ヒューリスティック(穴度)に戻す。"
                         "既定はv2(騎手質+地力+先行)で本線3着内 12.8%→21.5%に改善")
    ap.add_argument("--no-jockey", action="store_true",
                    help="騎手ファクターを外す(地力+先行+持続で評価)。"
                         "馬の中身だけで穴を見る用。検証では精度が下がる点に注意")
    ap.add_argument("--time-margin", type=float, default=0.8,
                    help="タイム適性の『際どい』判定幅[秒]。大きいほど足切りが緩む(既定0.8)")
    ap.add_argument("--keep-slow", action="store_true",
                    help="持ち時計が想定に届かない馬も足切りせず減点で残す"
                         "(消耗戦で粘る超人気薄=マイボンド型を拾う)")
    ap.add_argument("--attrition-meet", action="store_true",
                    help="時計超過の特別開催プリセット(今開催の川崎用)。"
                         "keep-slow + no-jockey + time-margin2.0 を一括適用する一時レジーム")
    ap.add_argument("--final", action="store_true",
                    help="高知ファイナル専用の再学習重み(実績を捨て騎手重視・差し寄り)を使う。"
                         "最終Rで指定。検証で本線3着内 16→20%")
    ap.add_argument("--samples", nargs="*", default=[
        "data/samples/nankan_2026-02.jsonl", "data/samples/nankan_2026-03.jsonl",
        "data/samples/nankan_2026-04.jsonl", "data/samples/nankan_2026-05.jsonl",
        "data/samples/nankan_2026-06.jsonl"])
    args = ap.parse_args()

    # 時計超過の特別開催プリセット: その開催だけの一時レジーム(汎用既定は変えない)。
    # 今開催の川崎のように全体に時計が掛かっている時、持ち時計の足切りを外し
    # (=遅い持続型を残す)、上位騎手ファクターも外す(=馬の中身で拾う)。
    if args.attrition_meet:
        args.keep_slow = True
        args.no_jockey = True
        args.time_margin = max(args.time_margin, 2.0)
        print("★今開催 特別運用[時計超過の重開催]: 時計足切り緩和 + 上位騎手ファクターOFF")
        print("  ※汎用の検証済みモデル(既定)とは別。この開催限定の一時設定です。")

    ymd = args.date.replace("-", "")
    client = PoliteClient()
    idx = client.get(CARD_URL.format(race_id=day_index_race_id(ymd, args.place)))
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[args.place]))
    if args.race not in races:
        raise SystemExit(f"{args.date} {args.place} {args.race}R が見つかりません。あるR: {sorted(races)}")
    rid = races[args.race]
    card = P.parse_card_page(client.get(CARD_URL.format(race_id=rid)), rid)

    jockeys = E.jockey_stats_from_card(card)
    trainers = trainer_stats_from_samples(args.samples)
    weights = weights_for(args.mode)
    # 上がりが使えない(前残り)馬場では、本ランキングにも脚質補正を効かせる
    agari_adj = agari_style_adjust(card) if args.mode in ("shomousen", "zenzan") else {}

    scores: dict[int, float] = {}
    rows = []
    for e in card.entries:
        if e.umaban is None:
            continue   # 馬番が取れない行(取消・パース欠け)はスキップ
        ctx = F.RaceContext(date=card.date, place=card.place, distance=card.distance,
                            field_size=card.field_size, jockey=e.jockey,
                            trainer=e.trainer, baba=args.baba)
        records = E.past_runs_to_records(e)
        feats = F.horse_features(records, ctx, jockeys=jockeys, trainers=trainers)
        sc = F.horse_score(records, ctx, jockeys=jockeys, trainers=trainers, weights=weights)
        sc += agari_adj.get(e.umaban, 0.0)   # 遅い上がり=持続型を加点 / 速い=割引
        scores[e.umaban] = sc
        rows.append((e, feats, sc))

    strengths = pb.strengths_from_scores(scores, temperature=args.temp)
    top3 = {um: pb.top3_probability(strengths, um) for um in scores}
    trio = sorted(pb.trio_probabilities(strengths).items(), key=lambda kv: -kv[1])
    trifecta = sorted(pb.trifecta_probabilities(strengths).items(), key=lambda kv: -kv[1])

    ranked = sorted(rows, key=lambda r: -r[2])
    mode_label = "消耗戦(タフネス・短間隔を加点)" if args.mode == "shomousen" else "通常"
    print(f"\n=== {card.place} {args.race}R {card.surface}{card.distance}m "
          f"/ 想定馬場: {BABA_FULL[args.baba]} / モード: {mode_label} ===")
    print(f"{'印':<2}{'馬番':>3} {'馬名':<11}{'騎手':<6}{'上位3着%':>7} "
          f"{'道悪':>6}{'脚質':>6}{'間隔':>6}{'叩':>3}{'タフ':>6}")
    for i, (e, feats, sc) in enumerate(ranked, 1):
        sig = E.running_signals(e, F.RaceContext(date=card.date, place=card.place,
              distance=card.distance, field_size=card.field_size, jockey=e.jockey,
              trainer=e.trainer, baba=args.baba), E.past_runs_to_records(e))
        print(f"{mark(i):<2}{str(e.umaban):>3} {e.horse_name[:10]:<11}"
              f"{(e.jockey or '')[:5]:<6}{top3[e.umaban]*100:>6.1f}% "
              f"{feats['baba_fit']:>+6.2f}{feats['senkou']:>+6.2f}"
              f"{str(sig['days_since_last'])+'日':>6}{sig['tatakii_n']:>3}{sig['toughness']:>6.2f}")

    print("\n--- 推奨買い目(モデル確率上位)---")
    print("三連複: " + " / ".join(f"{'-'.join(map(str,k))}({v*100:.1f}%)" for k, v in trio[:6]))
    print("三連単: " + " / ".join(f"{'→'.join(map(str,k))}({v*100:.2f}%)" for k, v in trifecta[:6]))
    if args.ana:
        tt = args.target_time
        note = "手動指定"
        if tt is None:
            tt, note = day_target_time(client, list(races.items()), card.distance)
        jrates = jockey_top3_from_samples(args.samples)
        # 重馬場の穴特徴量(厩舎道悪穴率+血統)は --wet-ana 指定時のみ有効。
        # 1210Rのリーク無しバックテストでエッジ無しと判明したため既定OFF(実験用に残す)。
        wet_stats = None
        if args.wet_ana:
            wet_stats = wet_ana_stats_from_samples(args.samples, pop_min=args.pop_min)
        bias = class_to_bias(card.race_class) if args.bias == "auto" else args.bias
        if args.bias == "auto":
            print(f"  (条件={card.race_class} → バイアス自動判定: {bias})")
        if args.wet_ana and args.baba in ("重", "不") and wet_stats and wet_stats.get("base"):
            print(f"  (重馬場特徴量ON[実験]: 道悪穴ベース{wet_stats['base']*100:.0f}% / "
                  f"厩舎{len(wet_stats['trainer'])}・種牡馬{len(wet_stats['sire'])}件)")
        # v2ランキング(既定ON): 検証で本線3着内 12.8%→21.5% に改善した再重み付け。
        v2_stats = None if args.legacy_ana else zubu_v2_stats_from_samples(
            args.samples, pop_min=args.pop_min)
        v2_weights = ZUBU_V2_WEIGHTS
        if args.final:
            v2_weights = ZUBU_V2_WEIGHTS_KOCHI_FINAL
            print("  (🏁高知ファイナル専用重み: 実績を捨て騎手重視・差し寄り。検証で本線3着内16→20%)")
        if args.no_jockey:
            v2_weights = {k: v for k, v in v2_weights.items() if k != "jockey"}
            print("  (騎手ファクターOFF: 地力+先行+持続で評価=精度低下に注意)")
        if args.keep_slow or args.time_margin != 0.8:
            print(f"  (タイム足切り緩和: margin={args.time_margin}"
                  f"{'・時計不足も残す' if args.keep_slow else ''})")
        picks = zubu_ana_picks(card, jockeys, target_time=tt, jockey_rates=jrates,
                               jockey_div=args.jw, pop_min=args.pop_min, bias=bias,
                               stab=args.stab, baba=args.baba, wet_stats=wet_stats,
                               v2_stats=v2_stats, v2_weights=v2_weights,
                               use_jockey=not args.no_jockey,
                               time_margin=args.time_margin, keep_slow=args.keep_slow)
        tt_s = f"{tt:.1f}秒({note})" if tt else "算出不可(確定レースなし)"
        rank_label = "旧穴度" if args.legacy_ana else "評価(v2)"
        print(f"\n--- ★ズブ穴ピックアップ({rank_label}順・騎手質+地力+先行軸)/ "
              f"想定勝ち時計 {tt_s} ---")
        if not picks:
            print("  該当なし")
        for e, score, tags in picks[:5]:
            print(f"  ◇{e.umaban:>2} {e.horse_name[:10]:<11}({e.exp_pop}人気) "
                  f"{rank_label}{score:+.2f}  {'・'.join(tags)}")

    print("\n※ オッズ未開放のためモデル確率での推奨。オッズ確定後は期待値(回収率)モードで再評価可。")


if __name__ == "__main__":
    main()
