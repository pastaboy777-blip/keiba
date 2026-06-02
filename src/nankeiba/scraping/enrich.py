"""出馬表(ParsedCard)を「前のセッションで重視した観点」を軸に充実化する。

コンセプト(README 参照): 南関は「ズブい馬を、陣営が手を尽くして今日のレースで
走らせにいくゲーム」。能力そのものより **今日その馬が走らせられているか** を読む。

出馬表の各馬の近走履歴(前5走)を core.interval.RunRecord に変換し、
core.features.horse_features で「走らせる」特徴量(出走間隔フィット・タフネス・
叩き良化・乗り替わり・騎手の追える力・場/距離替わり・使い込み疲労)を算出する。
結果(着順)が分かっていればラベルとして付与し、学習に使える1行に仕立てる。

依存: core(標準ライブラリのみ)。パースは parser.py(要 bs4)。
"""

from __future__ import annotations

from datetime import date

from ..core import interval as iv
from ..core import features as F
from .parser import ParsedCard, CardEntry, ParsedRace


def _d(s: str) -> date:
    y, m, dd = (int(x) for x in s.split("-"))
    return date(y, m, dd)


def past_runs_to_records(entry: CardEntry) -> list[iv.RunRecord]:
    """出馬表の近走(新しい順)を RunRecord 列に変換する。"""
    out: list[iv.RunRecord] = []
    for r in entry.recent_runs:
        if not r.date or r.finish_pos is None or not r.field_size:
            continue
        out.append(iv.RunRecord(
            date=r.date, place=r.place or "", distance=r.distance or 0,
            field_size=r.field_size, finish_pos=r.finish_pos,
            jockey=r.jockey, popularity=r.popularity, baba=r.baba,
            corner_pos=list(r.corner),
        ))
    return out


def jockey_stats_from_card(card: ParsedCard) -> F.ConnStats:
    """出馬表に載る各騎手の【勝率】から ConnStats(追える力の代理)を作る。"""
    rates: dict[str, float] = {}
    for e in card.entries:
        if e.jockey and e.jockey_win_rate is not None:
            rates[e.jockey] = e.jockey_win_rate / 100.0
    default = sum(rates.values()) / len(rates) if rates else 0.08
    return F.ConnStats(rates=rates, default=default)


def running_signals(entry: CardEntry, ctx: F.RaceContext,
                    records: list[iv.RunRecord]) -> dict:
    """人が読める「走らせる」観点の素データ(間隔・叩き・乗り替わり等)。"""
    prev = entry.recent_runs[0] if entry.recent_runs else None
    upcoming_days = None
    if prev and prev.date:
        upcoming_days = (_d(ctx.date) - _d(prev.date)).days
    profile = iv.build_profile(records)
    return {
        "days_since_last": upcoming_days,                       # 出走間隔[日]
        "interval_bucket": iv.interval_bucket(upcoming_days),   # 連闘/中1週/休み明け…
        "tatakii_n": F.starts_since_layoff(records, upcoming_days),  # 叩き○走目
        "toughness": round(profile.toughness, 3),               # ズブさ/タフネス
        "starts_last_90d": profile.starts_last_90d,             # 使われ具合
        "jockey_changed": bool(prev and prev.jockey and entry.jockey
                               and prev.jockey != entry.jockey),  # 乗り替わり
        "prev_jockey": prev.jockey if prev else None,
        "place_changed": bool(prev and prev.place and prev.place != ctx.place),
        "prev_place": prev.place if prev else None,
        "distance_change": (ctx.distance - prev.distance)
        if (prev and prev.distance) else None,
        "weight_diff": entry.horse_weight_diff,                 # 馬体重増減
    }


def build_enriched_race(card: ParsedCard, result: ParsedRace | None = None,
                        *, jockeys: F.ConnStats | None = None,
                        trainers: F.ConnStats | None = None) -> dict:
    """出馬表(+結果)から「走らせる」観点重視の充実レコード(dict)を作る。"""
    jockeys = jockeys or jockey_stats_from_card(card)
    trainers = trainers or F.ConnStats()
    finish_of = {}
    if result is not None:
        finish_of = {r.umaban: r.finish_pos for r in result.rows}

    horses = []
    for e in card.entries:
        ctx = F.RaceContext(
            date=card.date, place=card.place, distance=card.distance,
            field_size=card.field_size, jockey=e.jockey, trainer=e.trainer,
        )
        records = past_runs_to_records(e)
        feats = F.horse_features(records, ctx, jockeys=jockeys, trainers=trainers)
        horses.append({
            "umaban": e.umaban,
            "waku": e.waku,
            "horse_id": e.horse_id,
            "horse_name": e.horse_name,
            "sex_age": e.sex_age,
            "jockey": e.jockey,
            "jockey_affil": e.jockey_affil,
            "jockey_win_rate": e.jockey_win_rate,
            "jockey_top3_rate": e.jockey_top3_rate,
            "trainer": e.trainer,
            "weight_carried": e.weight_carried,
            "horse_weight": e.horse_weight,
            "exp_odds": e.exp_odds,
            "exp_pop": e.exp_pop,
            "finish_pos": finish_of.get(e.umaban),    # 結果(ラベル)
            "signals": running_signals(e, ctx, records),
            "features": {k: round(v, 4) for k, v in feats.items()},
            "recent_runs": [vars(r) for r in e.recent_runs],
        })

    return {
        "race_id": card.race_id,
        "date": card.date,
        "place": card.place,
        "distance": card.distance,
        "surface": card.surface,
        "field_size": card.field_size,
        "race_name": card.race_name,
        "result_order": [r.umaban for r in result.rows] if result else None,
        "horses": horses,
    }
