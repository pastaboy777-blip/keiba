#!/usr/bin/env python3
"""穴のrecall検証 ── 実際に来た穴を、うちのファクターで"事前に拾えたか"を採点する。

穴検出の自己評価が無い(=何を見落としたか分からない)課題を潰す。指定日の各レースで
好走した穴(6番人気以下で3着内)を列挙し、各馬が持っていたエッジ(小型/道悪巧者/短縮/差し/
血統湿)を数える。エッジ2つ以上=「拾えた」、0-1=「見落とし」として recall を算出。

使い方:
  python3 scripts/ana_recall.py --date 2026-07-17 --place 浦和 [--pop 6]

出力: 来た穴ごとに持っていたエッジと 拾/見落とし、開催の recall%、見落とし穴の特徴。
"""
import sys, argparse, datetime
sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
BAD = ("稍", "重", "不")
WET_SIRES = {"パイロ", "サウスヴィグラス", "ヘニーヒューズ", "クロフネ", "ゴールドアリュール",
             "エスポワールシチー", "シニスターミニスター", "マジェスティックウォリアー",
             "ドレフォン", "サンダースノー", "コパノリッキー", "ホッコータルマエ", "ゴールドドリーム"}


import re as _re
# 持続巡航(Hyperion)型＝垂れ率≈0 × 距離帯で上位の巡航速度。大井5-7月で人気薄複勝lift1.71。
_BAND_MED = {"短": 58.9, "マ": 56.5, "中": 56.0, "長": 55.4}  # 距離帯別 道中速度中央値(km/h・大井基準)
_HYPERION_SIRES = {"キンシャサノキセキ", "シルバーステート", "ストロングリターン", "ヘニーヒューズ",
                   "ダノンレジェンド", "パイロ", "シニスターミニスター", "キズナ"}
# グリップ血統＝「中山の急坂パワー＋重/不良のグリップ」を併せ持つ血統(サンデー系中山巧者＋ロベルト系)。
# 本人259レース検証：軸にはならない(全体複勝+0.8%)が、夏NARダート(白砂)の"大波乱の穴ヒモ"として本物
# (荒れ内複勝+10.2%・人気薄8番↓複勝は非該当の約3倍・20万三連単の69%に1頭以上絡む)。
# ★運用：人気薄(8番人気以下)のグリップ馬を三連単/三連複の穴ヒモに置く。軸には使わない(§18)。
_GRIP_SIRES = {"フジキセキ", "キンシャサノキセキ", "ネオユニヴァース", "ヴィクトワールピサ", "アルアイン",
               "ニシケンモノノフ", "エピファネイア", "シンボリクリスエス", "ブライアンズタイム",
               "タニノギムレット", "スクリーンヒーロー", "モーリス"}


def _tosec(t):
    m = _re.match(r'(?:(\d+):)?(\d+)\.(\d+)', str(t or ''))
    return (int(m.group(1)) if m and m.group(1) else 0) * 60 + int(m.group(2)) + int(m.group(3)) / 10 if m else None


def is_hyperion(pr):
    """前走が持続巡航型か＝垂れ率-1〜+2.5% かつ 道中速度が距離帯中央値以上。"""
    d, tt, ag = getattr(pr, "distance", None), _tosec(getattr(pr, "time", None)), getattr(pr, "agari", None)
    if not (d and tt and ag) or tt <= ag or ag <= 0:
        return False
    mid = (d - 600) / (tt - ag) * 3.6
    fin = 600 / ag * 3.6
    tare = (mid - fin) / mid * 100
    band = "短" if d <= 1200 else ("マ" if d <= 1600 else ("中" if d <= 1800 else "長"))
    return (-1.0 <= tare <= 2.5) and mid >= _BAND_MED.get(band, 99)


def pace_aptitude(e):
    """ペース適性 S/H/F/U を過去走の速度分解(垂れ率)から算出。TARGET指数の分類をデータ再現。
    S=瞬発力(スロー向き・終い大幅加速) / H=持続力(ハイ向き・垂れず高速巡航=持続巡航) /
    F=自在(両方の走りができる) / U=判別不能(データ不足)。
    運用：field_pace(§rule8)が「ハイ」ならH型、「スロー」ならS型が噛み合う＝加点。"""
    recs = e.recent_runs or []
    s = h = 0
    for pr in recs[:5]:
        d = getattr(pr, "distance", None)
        tt = _tosec(getattr(pr, "time", None))
        ag = getattr(pr, "agari", None)
        if not (d and tt and ag) or tt <= ag or ag <= 0:
            continue
        mid = (d - 600) / (tt - ag) * 3.6      # 道中速度 km/h
        fin = 600 / ag * 3.6                    # 終い速度 km/h
        tare = (mid - fin) / mid * 100          # 垂れ率(%)：負=終い加速/正=失速
        band = "短" if d <= 1200 else ("マ" if d <= 1600 else ("中" if d <= 1800 else "長"))
        if tare <= -3.0:                        # 終いを大きく加速＝瞬発(スロー向き)
            s += 1
        elif -1.0 <= tare <= 2.5 and mid >= _BAND_MED.get(band, 99):  # 垂れず高速巡航＝持続(ハイ向き)
            h += 1
    if s == 0 and h == 0:
        return "U"
    if s >= 1 and h >= 1 and abs(s - h) <= 1:
        return "F"
    return "H" if h >= s else "S"


def closer_grade(e):
    """終いの決め手の質を判定＝"本物の差し"か。強=位置を上げて好走を反復 / 弱=後方どまり。
    戻り値: '強' / '弱' / None"""
    recs = e.recent_runs or []
    closed = 0        # 後方から前進して好走した回数
    strong_last = False
    for i, pr in enumerate(recs[:4]):
        co = [x for x in (pr.corner or []) if isinstance(x, (int, float))]
        fs = pr.field_size or 12
        if not co:
            continue
        early, last = co[0], co[-1]
        gain = early - (pr.finish_pos or last)      # 序盤位置→着順で前進した数
        back = early > fs * 0.45                     # 序盤は後方
        good = pr.finish_pos and pr.finish_pos <= max(3, fs * 0.4)
        if back and gain >= 3 and good:              # 後方から差して好走
            closed += 1
            if i == 0 and gain >= 5:
                strong_last = True
    if closed >= 2 or strong_last:
        return "強"
    if closed >= 1:
        return "弱"
    return None


def field_pace(entries):
    """出走各馬の脚質から当日ペースを推定。前に行く馬が多い＝ハイ＝差し有利。"""
    n = len([e for e in entries if e.umaban]) or 1
    front = 0
    for e in entries:
        pr = e.recent_runs[0] if e.recent_runs else None
        co = [x for x in (pr.corner or []) if isinstance(x, (int, float))] if pr else []
        if co and co[0] <= max(3, round((pr.field_size or n) * 0.35)):
            front += 1
    ratio = front / n
    return "ハイ" if ratio >= 0.4 else ("スロー" if ratio <= 0.22 else "平均"), ratio


def agari_best(e, n=5):
    """近走の最速上がり3F(秒)。上がり3Fは600m固定区間なので距離補正不要。
    小さいほど終い優秀＝亀谷式「上がりT(上がり持ちタイム)」相当。"""
    vals = [getattr(pr, "agari", None) for pr in (e.recent_runs or [])[:n]]
    vals = [v for v in vals if v and v > 0]
    return min(vals) if vals else None


def agari_pattern(entries):
    """出走各馬の上がりP(=当日出走馬内での終い順位を0〜100で正規化)を返す {馬番: pct}。
    亀谷「スマート出馬表」の上がりP(距離帯内で終い順位をパターン化)をデータ再現。
    値が小さいほど終い上位(=高速上がり実績馬)。上がり3Fは固定区間なので距離補正不要。"""
    best = {}
    for e in entries:
        if not e.umaban:
            continue
        b = agari_best(e)
        if b:
            best[e.umaban] = b
    if not best:
        return {}
    order = sorted(best, key=lambda k: best[k])          # 終いが速い順
    n = len(order)
    return {um: round(i / max(1, n - 1) * 100) for i, um in enumerate(order)}


_REST_DAYS = 60  # 休み明けとみなす間隔(日)


def tataki_n(e, today):
    """今日が叩き何戦目か(§20検証済)。休み明け(60日+ギャップ)が無ければ0。
    復帰戦=1／その次=2…。人気薄で叩き1=lift0.54,叩き2=0.00(罠),叩き3以降=lift2.02(夏穴)。"""
    dates = []
    for pr in (e.recent_runs or []):
        try:
            if pr.date:
                dates.append(datetime.date.fromisoformat(pr.date))
        except Exception:
            pass
    if not dates or not today:
        return 0
    if (today - dates[0]).days >= _REST_DAYS:     # 今日とdates[0]の間が休み明け→今日=復帰戦
        return 1
    for i in range(len(dates) - 1):               # dates[i]が復帰戦→今日は(i+2)戦目
        if (dates[i] - dates[i + 1]).days >= _REST_DAYS:
            return i + 2
    return 0                                       # 連続出走で休み明けが射程外


def edges_for(e, today_dist, small_bias=True, pace=None, agari_pct=None, today=None):
    """馬のエッジ集合を返す（穴ファクター）。pace='ハイ'なら差し馬に想定加点。
    agari_pct=当日出走馬内の上がりP(0〜100・小さいほど終い上位)。today=当日(叩き判定用)。"""
    recs = e.recent_runs or []
    tags = set()
    cw = e.horse_weight or (recs[0].horse_weight if recs and recs[0].horse_weight else None)
    if cw and cw <= 458:
        tags.add("小型")
    elif cw and cw <= 466:
        tags.add("準小型")  # 459-466＝境界。小型バイアス日は拾う
    run = good = 0
    for pr in recs:
        if any(x in (pr.baba or "") for x in BAD):
            run += 1
            if pr.finish_pos and pr.finish_pos <= 3:
                good += 1
    if run and good >= 1 and good >= run * 0.5:
        tags.add("道悪巧者")
    dists = [pr.distance for pr in recs if pr.distance]
    if dists and today_dist and dists[0] and dists[0] > today_dist:
        tags.add("距離短縮")
    # 上がりP上位＝当日出走馬内で終い上位(高速上がり実績)。亀谷「上がりP」のデータ再現。
    if agari_pct is not None and agari_pct <= 40:
        tags.add("上がりP上位")
    # 亀谷式・差し穴フィルター＝「上がりP50以内 × 短縮」で人気薄の差し穴を炙る(2024雲雀S型)。
    # ※中央・芝のキレ決着で強い型。南関では"差し決着日(field_paceハイ・全体上がり速)"限定で有効。
    if agari_pct is not None and agari_pct <= 50 and "距離短縮" in tags:
        tags.add("上がりP×短縮")  # 差し決着日の○絞り込みシグナル
    # 差し＝(網)前走後方の緩タグは残しつつ、(質)強差し と (文脈)当日ハイペース想定を上乗せ。
    # 強差し×差し想定 が揃う馬＝差し穴の本線＝◎格上げ候補（精度用の高信頼シグナル）。
    if recs and recs[0].corner:
        co = [x for x in recs[0].corner if isinstance(x, (int, float))]
        fs = recs[0].field_size or 12
        if co and (co[0] > fs * 0.55 or co[-1] > fs * 0.55):
            tags.add("差し")            # 網（従来どおり・recallの下支え）
    grade = closer_grade(e)
    if grade == "強":
        tags.add("強差し")               # 質（本物の追い込み）
    if pace == "ハイ" and grade:
        tags.add("差し想定")             # 文脈（前が飛ぶ×差せる）
    # 持続巡航(Hyperion)型＝垂れない高速巡航＝上がり地味で群衆が見落とす過小評価穴(lift1.71)
    if recs and is_hyperion(recs[0]):
        tags.add("持続巡航")
    if any(s in (e.sire or "") for s in _HYPERION_SIRES):
        tags.add("持続血統")
    # グリップ血統(中山パワー×道悪グリップ)＝夏NAR白砂の大波乱の"穴ヒモ"(軸でなく人気薄ヒモ・§18)
    _ds = getattr(e, "dam_sire", "") or ""
    if any(s in (e.sire or "") for s in _GRIP_SIRES) or any(s in _ds for s in _GRIP_SIRES):
        tags.add("グリップ穴")
    sire = (e.sire or "")
    if any(s in sire for s in WET_SIRES):
        tags.add("血統湿")
    # 斤量減＝別定の恩恵(降級/未勝利継続/セ化/アローワンス)で軽くなった馬＝群衆が過小評価(大井lift1.43)
    wc = getattr(e, "weight_carried", None)
    pwc = recs[0].weight_carried if recs else None
    if wc and pwc and wc - pwc <= -1:
        tags.add("斤量減")
    # 乗替↑＝前走と別騎手 かつ 今回が勝率の高い騎手＝厩舎の勝負気配（"エッジ無"穴を埋める新factor）
    jw = getattr(e, "jockey_win_rate", None)
    prev_j = recs[0].jockey if recs else None
    if e.jockey and prev_j and e.jockey != prev_j and jw and jw >= 18:
        tags.add("乗替トップ騎手")  # トップ騎手への勝負乗替のみ(発火絞り＝精度シグナル)
    # 叩き3戦目以降(§20/§20-B南関1053R検証)＝単独では複勝lift1.15の弱い上積み。
    # ただしマ〜中距離帯に限ると1.34-1.41で有効・短長帯は無効(0.80-0.91)。
    # そこで「マ〜中距離 かつ 叩き3戦目以降」でのみ点灯(距離条件で精度を上げる)。
    # ※復帰戦(1)=lift0.97,叩き2戦目=0.91と大差なく、小サンプルの「罠/lift2.0」は誤り(§20-B)。
    if today is not None and today_dist and 1300 <= today_dist <= 1900:
        _tn = tataki_n(e, today)
        if isinstance(_tn, int) and _tn >= 3:
            tags.add("叩き3戦目穴")
    return tags, cw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--pop", type=int, default=6, help="この人気以下を穴とする")
    ap.add_argument("--small-bias", action="store_true",
                    help="小型有利が確定した日用＝小型1つで拾える(bias_forecastが小型[信頼高]の時に付ける)")
    a = ap.parse_args()
    c = PoliteClient()
    ymd = a.date.replace("-", "")
    today = datetime.date.fromisoformat(a.date)
    idx = c.get(CARD.format(r=day_index_race_id(ymd, a.place)), use_cache=True)
    races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[a.place]))
    caught = missed = 0
    miss_detail = []
    print(f"=== 穴recall検証: {a.date} {a.place} (穴={a.pop}番人気以下で3着内) ===")
    for R in sorted(races):
        try:
            rr = P.parse_result_page(c.get(PERF.format(r=races[R]), use_cache=True), races[R])
            if not rr.rows or not rr.rows[0].finish_pos:
                continue
            _chtml = c.get(CARD.format(r=races[R]), use_cache=True)
            pc = P.parse_card_page(_chtml, races[R])
            try:
                from rakuten_ped import attach as _attach_ped
                _attach_ped(_chtml, pc.entries)   # 母父をインライン付与(グリップ/中山型が母父込みで発火)
            except Exception:
                pass
        except Exception:
            continue
        emap = {e.umaban: e for e in pc.entries}
        dist = getattr(pc, "distance", None)
        pace, _ = field_pace(pc.entries)
        apct = agari_pattern(pc.entries)
        for row in rr.rows:
            if row.finish_pos and row.finish_pos <= 3 and row.popularity and row.popularity >= a.pop:
                e = emap.get(row.umaban)
                if not e:
                    continue
                tags, cw = edges_for(e, dist, pace=pace, agari_pct=apct.get(row.umaban), today=today)
                # 小型バイアス日は「小型」単独でも拾える（①が小型[信頼高]の時）
                ok = len(tags) >= 2 or (a.small_bias and "小型" in tags)
                mark = "拾✓" if ok else "見✗"
                if ok:
                    caught += 1
                else:
                    missed += 1
                    miss_detail.append((R, row.horse_name, row.popularity, tags))
                print(f"  {R:>2}R {row.finish_pos}着 {row.horse_name[:9]:9s} {row.popularity:>2}人気 体{cw} [{mark}] {'/'.join(sorted(tags)) or 'エッジ無'}")
    tot = caught + missed
    print(f"\n--- recall = {caught}/{tot} = {caught/tot:.0%} (穴のうちエッジ2つ以上で拾えた割合) ---" if tot else "対象穴なし")
    if miss_detail:
        print("見落とし穴（次に強化すべき盲点）:")
        for R, nm, pop, tags in miss_detail:
            print(f"  {R}R {nm[:9]} {pop}人気 : 保有エッジ={'/'.join(sorted(tags)) or 'なし'}")


if __name__ == "__main__":
    main()
