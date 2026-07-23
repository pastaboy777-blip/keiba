"""新聞風の「指数＆展開予想」ビューを組み立ててレンダリングする。

実物の南関競馬新聞のうち、本パイプラインで再現する中核=
  ・展開予想「3走以内の通過順」6マスグリッド (pace.py)
  ・スピード指数と、その一覧サマリー (hindex.py / summary.py)
  ・指数つき簡易馬柱(過去5走: 日付/場/距離/馬場/着順/タイム/通過順/指数)
をまとめ、テキスト or HTML に出力する。

依存ライブラリなし(標準ライブラリのみ)。
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Sequence

from .interval import RunRecord
from .hindex import SpeedIndexModel, normalize_going
from . import pace as pc
from . import summary as sm
from . import composite as cp
from . import pace_aptitude as pa
from . import mirage as mir
from . import grip as grp
from . import smart as sma
from . import pedigree as ped
from . import ped_stats as pst


# ---------------------------------------------------------------------------
# 入力データ構造
# ---------------------------------------------------------------------------

@dataclass
class PaperEntry:
    """新聞に載せる1頭分。"""
    umaban: int
    name: str
    history: list[RunRecord] = field(default_factory=list)   # 新しい順
    sex_age: str | None = None       # 例 "牝3"
    jockey: str | None = None
    trainer: str | None = None
    waku: int | None = None
    sire: str | None = None          # 父(種牡馬)
    bms: str | None = None           # 母父(BMS)


@dataclass
class RaceHeader:
    place: str
    distance: int
    date: str
    race_no: int | None = None
    baba: str | None = None
    post_time: str | None = None
    race_name: str | None = None


# ---------------------------------------------------------------------------
# 指数印(新聞の◎○▲△など): 場内の相対順位で付与
# ---------------------------------------------------------------------------

MARKS = ["◎", "○", "▲", "△", "△"]


def _best_index(runs: Sequence[RunRecord], model: SpeedIndexModel, lookback: int):
    best = None
    for rec in list(runs)[:lookback]:
        idx = model.index(rec)
        if idx is None:
            continue
        if best is None or idx > best:
            best = idx
    return best


@dataclass
class HorseView:
    entry: PaperEntry
    idx_best2: float | None       # 近2走以内の最高指数(上段)
    idx_best5: float | None       # 近5走以内の最高指数(下段)
    mark: str = ""                # 印(総合指数の場内順位)
    comp: "cp.Composite | None" = None   # 総合指数(素+展開±馬場)
    pace_apt: str = "U"           # ペース適性 S/H/F/U(+激)
    mirage: "mir.Mirage | None" = None   # 見かけ倒し指数の警告
    grip: "grp.GripTag | None" = None    # グリップ血統(夏NAR大波乱の穴ヒモ)


@dataclass
class RaceCard:
    header: RaceHeader
    horses: list[HorseView]
    grid: pc.PaceGrid
    top10: list[sm.IndexRow]
    same_track: list[sm.IndexRow]
    first3f: list[sm.First3FRow]
    model: SpeedIndexModel
    going_apt: dict[int, sm.GoingAptitude] = field(default_factory=dict)
    smart: dict[int, "sma.SmartRow"] = field(default_factory=dict)
    agari_top: list[tuple[int, float]] = field(default_factory=list)
    ped_tags: dict[int, "ped.PedTag"] = field(default_factory=dict)
    ped_bias: "ped.PedBias | None" = None


def build_card(
    header: RaceHeader,
    entries: Sequence[PaperEntry],
    model: SpeedIndexModel,
) -> RaceCard:
    """出走馬と指数モデルから新聞1レース分のカードを組み立てる。"""
    hist = [(e.umaban, e.history) for e in entries]

    grid = pc.build_pace_grid(hist)
    top10 = sm.top_index_last10(hist, model, lookback=10)
    same_track = sm.same_track_index_top(hist, model, header.place, lookback=10)
    first3f = sm.first3f_top(hist, header.distance, lookback=5)
    going_apt = sm.going_aptitude(hist, model, header.baba) if header.baba else {}
    smart = sma.smart_table(hist, header.distance)
    agari_top = sma.agari_t_top(hist)
    ped_tags = ped.tag_entries([(e.umaban, e.sire, e.bms) for e in entries])
    ped_bias = ped.bias_of(ped_tags)

    ctx = cp.PaceContext.from_grid(grid, header.baba)
    views = []
    for e in entries:
        b5 = _best_index(e.history, model, 5)
        comp = cp.composite_index(b5, e.history, ctx, going_apt.get(e.umaban))
        mrg = mir.detect(e.history, model, header.place, header.distance)
        gtag = grp.grip_of(e.sire, e.bms)
        views.append(HorseView(
            entry=e,
            idx_best2=_best_index(e.history, model, 2),
            idx_best5=b5,
            comp=comp,
            pace_apt=pa.pace_aptitude_mark(e.history),
            mirage=mrg if mrg else None,
            grip=gtag if gtag else None,
        ))
    # 印: 総合指数の場内順位上位から ◎○▲△△(総合が無い馬は素指数で代替)
    def _rank_key(v: HorseView):
        if v.comp and v.comp.total is not None:
            return v.comp.total
        return v.idx_best5 if v.idx_best5 is not None else -1e9
    ranked = sorted(
        [v for v in views if (v.comp and v.comp.total is not None) or v.idx_best5 is not None],
        key=_rank_key, reverse=True,
    )
    for i, v in enumerate(ranked[:len(MARKS)]):
        v.mark = MARKS[i]

    return RaceCard(
        header=header, horses=views, grid=grid,
        top10=top10, same_track=same_track, first3f=first3f, model=model,
        going_apt=going_apt, smart=smart, agari_top=agari_top,
        ped_tags=ped_tags, ped_bias=ped_bias,
    )


# ---------------------------------------------------------------------------
# テキスト出力
# ---------------------------------------------------------------------------

def _fmt_idx(x: float | None) -> str:
    if x is None:
        return "  -"
    return f"{x:+.0f}"


def render_text(card: RaceCard) -> str:
    h = card.header
    L: list[str] = []
    title = f"{h.place} {h.race_no or ''}R {h.distance}m"
    if h.baba:
        title += f" {h.baba}"
    title += f"  {h.date}"
    if h.post_time:
        title += f" {h.post_time}"
    L.append(title)
    if h.race_name:
        L.append(h.race_name)
    L.append("=" * 56)

    # 展開予想グリッド
    L.append("【展開予想 — 3走以内の通過順】")
    L.append(f"  ペース読み: {card.grid.pace_read(h.baba)}  (左2マス={card.grid.front_count()}頭)")
    L.append("  ┌─ 5着以内 ────────────────────────┬─ 6着以降 ──┐")
    hdr = ["逃げ", "3・4角3内", "4角3内", "4角4外", "逃げ", "3・4角3内"]
    for (key, label, in5), name in zip(pc.BUCKETS, hdr):
        cell = card.grid.cell(key)
        L.append(f"  [{name:<8}] {cell.display()}")
    L.append("")

    # 10走以内 指数上位
    L.append("【10走以内 指数上位】(馬番 指数 / 何走前 場 距離 馬場 日付)")
    for r in card.top10[:12]:
        L.append(
            f"  {r.umaban:>2}  {r.index:+.0f}  /{r.runs_ago}走前 "
            f"{r.place} {r.distance} {r.baba or ''} {r.date}"
        )
    L.append("")

    # 馬場適性(今回の馬場が渋っているときに表示)
    if card.going_apt and h.baba and h.baba[:1] in ("稍", "重", "不"):
        apt = [a for a in card.going_apt.values() if a.n > 0]
        apt.sort(key=lambda a: (a.best_index if a.best_index is not None else -99), reverse=True)
        L.append(f"【馬場適性({h.baba}系)】(馬番 最高指数 複勝率 該当走数)")
        for a in apt[:10]:
            bi = f"{a.best_index:+.0f}" if a.best_index is not None else "  -"
            L.append(f"  {a.umaban:>2}  {bi}  複{a.in3_rate:.0%}  ({a.n}走)")
        L.append("")

    # 同競馬場 指数上位
    if card.same_track:
        L.append(f"【同競馬場({h.place})指数上位】")
        L.append("  " + "  ".join(f"{r.umaban}({r.index:+.0f})" for r in card.same_track[:10]))
        L.append("")

    # 前3F上位
    if card.first3f:
        L.append(f"【前3Fタイム上位】(今回{h.distance}m ±200m・概算)")
        L.append("  " + "  ".join(f"{r.umaban}({r.first3f:.1f})" for r in card.first3f))
        L.append("")

    # 上がりT上位(スマート出馬表・亀谷式) + ローテ
    if card.agari_top:
        L.append("【上がりT上位】(馬番 上がり最速/近3走・ローテ) ※差し決着で狙い")
        cells = []
        for um, at in card.agari_top:
            rot = card.smart[um].rot if um in card.smart else ""
            cells.append(f"{um}({at:.1f}{rot})")
        L.append("  " + "  ".join(cells))
        L.append("")

    # 大系統(血統ビーム)バイアス
    if card.ped_bias and card.ped_bias.total:
        b = card.ped_bias
        L.append("【大系統バイアス(血統ビーム)】")
        L.append("  父の大系統: " + " ".join(
            f"{ped.system_name(k)}{v}" for k, v in b.top_systems(5)))
        L.append(f"  父or母父サンデー系: {b.sunday_line}/{b.total}  →  {b.track_read('ダ')}")
        L.append("")

    # 出走各馬 総合指数(印は総合順)
    L.append("【出走各馬 総合指数】(印 馬番 馬名  総合 = 素指数 展開 馬場 / 脚質 / ペース適性)")
    order = sorted(card.horses,
                   key=lambda v: (v.comp.total if v.comp and v.comp.total is not None else -1e9),
                   reverse=True)
    for v in order:
        e = v.entry
        c = v.comp
        total = _fmt_idx(c.total if c else None)
        brk = c.breakdown() if c else "-"
        style = (c.style if c and c.style else "―")
        sr = card.smart.get(e.umaban)
        smart_s = f"  {sr.fmt()}" if sr else ""
        pt = card.ped_tags.get(e.umaban)
        ped_s = ""
        if pt and pt.sire_sys:
            fm = pst.fit(pt.sire_sys, h.distance)
            ped_s = f"  血統[{ped.system_name(pt.sire_sys)}{fm}]"
        L.append(
            f"  {v.mark or '  '} {e.umaban:>2} {e.name:<12} "
            f"総合{total:>4}  ({brk})  {style}  ペース{v.pace_apt}{smart_s}{ped_s}"
        )
    return "\n".join(L)


# ---------------------------------------------------------------------------
# HTML 出力(新聞レイアウト再現)
# ---------------------------------------------------------------------------

def _going_class(baba: str | None) -> str:
    g = normalize_going(baba)
    return {"良": "b-ryo", "稍": "b-yaya", "重": "b-omo", "不": "b-fu"}.get(g or "", "")


def _corner_str(cp) -> str:
    return "-".join(str(c) for c in (cp or []) if c)


def _ped_badge(pt, distance: int = 0) -> str:
    """父の大系統を色付きバッジで。母父サンデー系は小印、距離帯フィットは○/▽。"""
    if pt is None or not pt.sire_sys:
        return ""
    col = ped.system_color(pt.sire_sys)
    nm = ped.system_name(pt.sire_sys)
    fitmark = pst.fit(pt.sire_sys, distance) if distance else ""
    fit = f"<span class='pedfit'>{fitmark}</span>" if fitmark else ""
    bms = ""
    if pt.bms_sys:
        bms = f"<span class='bms' title='母父{ped.system_name(pt.bms_sys)}'>母父{ped.short_name(pt.bms_sys)}</span>"
    return (f"<div class='ped'><span class='pedtag' style='background:{col}'>{nm}</span>{fit}{bms}</div>")


def render_html(card: RaceCard, *, title: str | None = None,
                pace_note: str | None = None) -> str:
    h = card.header
    esc = html.escape
    doc_title = title or f"{h.place}{h.race_no or ''}R {h.distance}m 指数＆展開予想"

    # --- 各馬の簡易馬柱行 ---
    def horse_row(v: HorseView) -> str:
        e = v.entry
        cells = []
        for rec in e.history[:5]:
            idx = card.model.index(rec)
            idx_txt = f"{idx:+.0f}" if idx is not None else "―"
            t = f"{rec.time_sec:.1f}" if rec.time_sec is not None else "―"
            dline = (f"{esc(rec.date[5:])} {esc(rec.place)} {rec.distance}"
                     f"<span class='baba {_going_class(rec.baba)}'>{esc(rec.baba or '')}</span>")
            cells.append(
                f"<td class='run'>"
                f"<div class='rl1'>{dline}</div>"
                f"<div class='rl2'>{rec.finish_pos}着 <b>{t}</b> "
                f"<span class='corner'>{_corner_str(rec.corner_pos)}</span></div>"
                f"<div class='ridx'>{idx_txt}</div>"
                f"</td>"
            )
        while len(cells) < 5:
            cells.append("<td class='run empty'></td>")
        mark = v.mark or ""
        return (
            f"<tr>"
            f"<td class='um um{((e.umaban - 1) % 8) + 1}'>{e.umaban}</td>"
            f"<td class='horse'>"
            f"<div class='mark'>{mark}</div>"
            f"<div class='hn'>{esc(v.entry.name)}</div>"
            f"<div class='meta'>{esc(v.entry.sex_age or '')} {esc(v.entry.jockey or '')}</div>"
            f"<div class='smart'>{esc(card.smart[e.umaban].fmt()) if e.umaban in card.smart else ''}</div>"
            f"{_ped_badge(card.ped_tags.get(e.umaban), h.distance)}"
            f"</td>"
            f"<td class='idx'>"
            f"<div class='i2'>{_fmt_idx(v.comp.total if v.comp else v.idx_best5)}</div>"
            f"<div class='i5'>{esc(v.comp.breakdown() if v.comp else '')}</div>"
            f"<div class='style'>{esc(v.comp.style if (v.comp and v.comp.style) else '')}"
            f"<span class='pace'>{esc(v.pace_apt)}</span></div>"
            f"</td>"
            + "".join(cells) +
            f"</tr>"
        )

    horse_rows = "\n".join(horse_row(v) for v in card.horses)

    # --- 展開グリッド ---
    def grid_cell(key: str) -> str:
        cell = card.grid.cell(key)
        if cell.overflow:
            body = "<span class='over'>―(10頭超)</span>"
        else:
            body = "".join(f"<span class='pnum'>{u}</span>" for u in cell.umaban) or "<span class='none'>―</span>"
        return f"<div class='gcell'><div class='glabel'>{esc(cell.label)}</div><div class='gbody'>{body}</div></div>"

    grid_in5 = "".join(grid_cell(k) for k in pc.IN5_KEYS)
    grid_out = "".join(grid_cell(k) for k in pc.OUT_KEYS)

    # --- サマリー ---
    top10_rows = "".join(
        f"<tr><td class='sn'>{r.umaban}</td><td class='si'>{r.index:+.0f}</td>"
        f"<td>{r.runs_ago}走前</td><td>{esc(r.place)}</td><td>{r.distance}</td>"
        f"<td>{esc(r.baba or '')}</td><td class='sd'>{esc(r.date)}</td></tr>"
        for r in card.top10[:14]
    )
    same_track = " ".join(
        f"<span class='chip'>{r.umaban}<b>{r.index:+.0f}</b></span>" for r in card.same_track[:12]
    ) or "―"
    wet_today = bool(h.baba and h.baba[:1] in ("稍", "重", "不"))
    going_block = ""
    if wet_today and card.going_apt:
        apt = [a for a in card.going_apt.values() if a.n > 0]
        apt.sort(key=lambda a: (a.best_index if a.best_index is not None else -99), reverse=True)
        chips = " ".join(
            f"<span class='chip'>{a.umaban}<b>{a.best_index:+.0f}</b>"
            f"<span class='sub2'>複{a.in3_rate:.0%}</span></span>"
            for a in apt[:12]
        ) or "―"
        going_block = (
            f"<div class='stitle' style='margin-top:12px;border-color:#0b57d0'>"
            f"馬場適性（{esc(h.baba)}系・最高指数/複勝率）</div><div>{chips}</div>"
        )

    # 大系統バイアス(血統ビーム)
    ped_block = ""
    if card.ped_bias and card.ped_bias.total:
        b = card.ped_bias
        chips = " ".join(
            f"<span class='chip' style='border-color:{ped.system_color(k)}'>"
            f"<span class='pd' style='background:{ped.system_color(k)}'></span>"
            f"{esc(ped.system_name(k))}<b>{v}</b></span>"
            for k, v in b.top_systems(6)
        )
        ped_block = (
            f"<div class='stitle' style='margin-top:12px;border-color:#e5007f'>大系統バイアス（血統ビーム）</div>"
            f"<div>{chips}</div>"
            f"<div class='note-ped'>父or母父サンデー系 {b.sunday_line}/{b.total}"
            f" → {esc(b.track_read('ダ'))}</div>"
        )
    first3f = " ".join(
        f"<span class='chip'>{r.umaban}<b>{r.first3f:.1f}</b></span>" for r in card.first3f
    ) or "―"
    agari_top = " ".join(
        f"<span class='chip'>{um}<b>{at:.1f}</b>"
        f"<span class='sub2'>{esc(card.smart[um].rot) if um in card.smart else ''}</span></span>"
        for um, at in card.agari_top
    ) or "―"

    baba_txt = f" ({esc(h.baba)})" if h.baba else ""
    subttl = f"{esc(h.date)}　{esc(h.post_time or '')}"

    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(doc_title)}</title>
<style>
:root {{
  --line:#222; --bg:#fff; --ink:#111; --sub:#666;
  --pink:#ffe0ea; --blue:#0b57d0; --orange:#ff7a00; --grid:#e6e6e6;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#f3f2ee; color:var(--ink);
  font-family:"Hiragino Kaku Gothic ProN","Yu Gothic",Meiryo,system-ui,sans-serif;
  font-size:13px; -webkit-text-size-adjust:100%; }}
.paper {{ max-width:1080px; margin:14px auto; background:var(--bg);
  border:2px solid var(--line); }}
.masthead {{ display:flex; align-items:center; gap:12px; padding:8px 12px;
  border-bottom:3px solid var(--line); background:#111; color:#fff; }}
.masthead .rno {{ font-size:22px; font-weight:900; background:#fff; color:#111;
  border-radius:4px; padding:1px 9px; }}
.masthead .place {{ font-size:22px; font-weight:900; letter-spacing:2px; }}
.masthead .dist {{ font-size:26px; font-weight:900; }}
.masthead .sub {{ margin-left:auto; font-size:12px; color:#ddd; text-align:right; }}
h2 {{ font-size:14px; margin:0; padding:6px 12px; background:#111; color:#fff;
  letter-spacing:1px; }}
.section {{ padding:10px 12px; border-bottom:1px solid var(--line); }}
/* 展開グリッド */
.pace-read {{ font-weight:700; margin-bottom:6px; }}
.pace-read .fc {{ color:var(--blue); }}
.grid-wrap {{ display:flex; gap:8px; align-items:stretch; }}
.grp {{ border:2px solid var(--line); }}
.grp .cap {{ background:#333; color:#fff; text-align:center; font-weight:700;
  padding:2px; font-size:12px; }}
.grp .row {{ display:flex; }}
.gcell {{ width:150px; border-right:1px solid var(--grid); }}
.gcell:last-child {{ border-right:none; }}
.grp.out .gcell {{ width:130px; }}
.glabel {{ background:#f0efe9; border-bottom:1px solid var(--grid); text-align:center;
  font-weight:700; padding:3px; font-size:12px; }}
.gbody {{ min-height:64px; padding:6px; display:flex; flex-wrap:wrap; gap:5px 6px;
  align-content:flex-start; }}
.pnum {{ display:inline-flex; align-items:center; justify-content:center; min-width:22px;
  height:22px; border:1px solid #333; border-radius:3px; font-weight:700; background:#fff; }}
.none,.over {{ color:var(--sub); }}
/* サマリー */
.cols {{ display:flex; gap:14px; flex-wrap:wrap; }}
.col {{ flex:1; min-width:280px; }}
.stitle {{ font-weight:800; border-left:5px solid var(--orange); padding-left:6px;
  margin-bottom:5px; }}
table.sum {{ border-collapse:collapse; width:100%; font-size:12px; }}
table.sum td {{ border:1px solid var(--grid); padding:1px 5px; text-align:center; }}
table.sum td.sn {{ font-weight:800; background:#f6f5f1; }}
table.sum td.si {{ font-weight:800; color:var(--blue); }}
table.sum td.sd {{ color:var(--sub); }}
.chip {{ display:inline-block; border:1px solid #ccc; border-radius:12px; padding:1px 8px;
  margin:2px 2px; background:#fafafa; }}
.chip b {{ color:var(--blue); margin-left:3px; }}
.chip .sub2 {{ color:var(--sub); margin-left:4px; font-size:11px; }}
/* 馬柱 */
.uma {{ overflow-x:auto; }}
table.bacho {{ border-collapse:collapse; width:100%; }}
table.bacho td {{ border:1px solid #d8d8d8; vertical-align:top; }}
td.um {{ width:26px; text-align:center; font-weight:900; color:#fff; font-size:15px; }}
.um1{{background:#111}}.um2{{background:#111}}.um3{{background:#d23}}.um4{{background:#1a63c4}}
.um5{{background:#f5c518;color:#111}}.um6{{background:#1a9e3b}}.um7{{background:#f60;}}.um8{{background:#d23}}
td.horse {{ width:118px; padding:3px 5px; }}
td.horse .mark {{ float:right; font-size:18px; font-weight:900; }}
td.horse .hn {{ font-weight:800; font-size:14px; }}
td.horse .meta {{ color:var(--sub); font-size:11px; }}
td.horse .smart {{ color:#1a6b2f; font-size:10px; margin-top:1px; }}
td.horse .ped {{ margin-top:2px; }}
td.horse .ped .pedtag {{ color:#fff; font-size:10px; font-weight:700; border-radius:3px;
  padding:0 5px; }}
td.horse .ped .bms {{ color:var(--sub); font-size:10px; margin-left:3px; }}
td.horse .ped .pedfit {{ font-weight:900; margin-left:3px; color:#c0007a; }}
.chip .pd {{ display:inline-block; width:9px; height:9px; border-radius:2px; margin-right:4px;
  vertical-align:middle; }}
.note-ped {{ margin-top:5px; font-size:12px; color:#8a1a5a; font-weight:600; }}
td.idx {{ width:66px; text-align:center; }}
td.idx .i2 {{ font-weight:900; font-size:17px; }}
td.idx .i5 {{ color:var(--sub); border-top:1px dashed #ccc; font-size:10px; line-height:1.3; }}
td.idx .style {{ font-size:10px; color:#fff; background:#666; border-radius:8px;
  display:inline-block; padding:0 6px; margin-top:2px; }}
td.idx .pace {{ margin-left:3px; color:#fff; background:#0b57d0; border-radius:8px;
  padding:0 5px; font-weight:700; }}
td.run {{ width:104px; padding:2px 4px; position:relative; }}
td.run.empty {{ background:#faf9f6; }}
.rl1 {{ font-size:11px; color:#333; }}
.rl2 {{ font-size:12px; }}
.rl2 b {{ font-size:13px; }}
.corner {{ color:var(--blue); }}
.ridx {{ position:absolute; right:3px; bottom:2px; font-weight:900;
  border:1px solid #333; border-radius:3px; padding:0 4px; background:#fff; font-size:12px; }}
.baba {{ font-weight:700; padding:0 2px; border-radius:2px; }}
.b-yaya{{background:#eef}}.b-omo{{background:#ccd; }}.b-fu{{background:#111;color:#fff}}
thead td {{ background:#333; color:#fff; text-align:center; font-weight:700; }}
.foot {{ padding:8px 12px; color:var(--sub); font-size:11px; }}
.note-box {{ background:#fff7e6; border:1px solid #f0c36d; border-radius:4px;
  padding:6px 9px; margin-bottom:8px; font-size:12px; color:#8a5a00; }}
</style></head>
<body>
<div class="paper">
  <div class="masthead">
    <span class="rno">{h.race_no or ''}</span>
    <span class="place">{esc(h.place)}</span>
    <span class="dist">{h.distance}m{baba_txt}</span>
    <span class="sub">{subttl}<br>{esc(h.race_name or '')}</span>
  </div>

  <h2>展開予想 — 3走以内の通過順</h2>
  <div class="section">
    {f'<div class="note-box">{esc(pace_note)}</div>' if pace_note else ''}
    <div class="pace-read">ペース読み：{esc(card.grid.pace_read(h.baba))}
      <span class="fc">（左2マス＝{card.grid.front_count()}頭）</span></div>
    <div class="grid-wrap">
      <div class="grp in5"><div class="cap">5着以内だった走</div><div class="row">{grid_in5}</div></div>
      <div class="grp out"><div class="cap">6着以降だった走</div><div class="row">{grid_out}</div></div>
    </div>
    <div class="foot">同じマスの人気馬に注意（能力上位馬に潰される他馬）。相手は別マスから。
      左2マスが手薄なら前残り＝人気薄の逃げ・先行にも警戒。</div>
  </div>

  <h2>指数サマリー</h2>
  <div class="section">
    <div class="cols">
      <div class="col">
        <div class="stitle">10走以内 指数上位</div>
        <table class="sum">
          <thead><tr><td>馬番</td><td>指数</td><td>何走前</td><td>場</td><td>距離</td><td>馬場</td><td>日付</td></tr></thead>
          {top10_rows}
        </table>
      </div>
      <div class="col">
        <div class="stitle">同競馬場（{esc(h.place)}）指数上位</div>
        <div>{same_track}</div>
        <div class="stitle" style="margin-top:12px">前3Fタイム上位（{h.distance}m±200m・概算）</div>
        <div>{first3f}</div>
        <div class="stitle" style="margin-top:12px;border-color:#1a9e3b">上がりT上位（近3走最速・差し決着で狙い／ローテ付）</div>
        <div>{agari_top}</div>
        {going_block}
        {ped_block}
      </div>
    </div>
  </div>

  <h2>指数つき馬柱（過去5走：左＝前走）</h2>
  <div class="section uma">
    <table class="bacho">
      <thead><tr><td>番</td><td>馬名／騎手</td><td>総合<br>指数</td>
        <td>前走</td><td>2走前</td><td>3走前</td><td>4走前</td><td>5走前</td></tr></thead>
      {horse_rows}
    </table>
  </div>

  <div class="foot">
    総合指数＝スピード指数（素）＋馬場補正。素指数＝10×(par(距離)＋当日馬場差B−走破タイム)。
    馬場補正＝今回の馬場での複勝実績（渋った馬場時のみ）。展開グリッド・脚質は参考表示で、
    指数の上書きはしない（実データ検証で展開の加点は的中を下げたため）。印◎○▲△は総合指数の場内上位順。
    ※本紙は実物新聞のロジックを参考にした独自実装。
  </div>
</div>
</body></html>"""
