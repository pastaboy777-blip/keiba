#!/usr/bin/env python3
"""キーストーン収束(§22)を我々のrakuten父/母父データで全スケール裏取り。
netkeiba不要(全キャッシュ)。ロベルト系(グリップ中核)とミスプロ系ダートパワーを、
父/母父別・両側二重濃縮・道悪別に人気薄複勝率liftで測る。深さは2代(父+母父)=下限値。
使い方: python3 scripts/blood_val.py --from 2026-04-01 --to 2026-07-24
"""
import sys, argparse, datetime
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from nankeiba.scraping.race_id import day_index_race_id, ALL_CODES
from nankeiba.scraping.client import PoliteClient
from nankeiba.scraping import parser as P

CARD = "https://keiba.rakuten.co.jp/race_card/list/RACEID/{r}"
PERF = "https://keiba.rakuten.co.jp/race_performance/list/RACEID/{r}"
BAD = ("稍", "重", "不")

# ロベルト系(グリップ中核・§18/§22でkeystoneが再発見したクラスター)
ROBERTO = {"ロベルト", "ブライアンズタイム", "タニノギムレット", "シンボリクリスエス",
           "エピファネイア", "スクリーンヒーロー", "モーリス", "グラスワンダー", "シルバーステート"}
# ミスプロ系ダートパワー(フォーティナイナー/ミスプロ系・keystoneのもう一本の柱)
MRPROSPECTOR = {"フォーティナイナー", "サウスヴィグラス", "エンドスウィープ", "アドマイヤムーン",
                "シニスターミニスター", "パイロ", "マジェスティックウォリアー", "カジノドライヴ",
                "ヘニーヒューズ", "アジャストザヘッジ", "スウェプトオーヴァーボード"}


def has(name, S):
    n = (name or "").strip()
    return any(s in n for s in S) if n else False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True)
    ap.add_argument("--to", dest="to", required=True)
    ap.add_argument("--usui", type=int, default=6)
    ap.add_argument("--tracks", default="浦和,船橋,大井,川崎")
    a = ap.parse_args()
    c = PoliteClient()
    tracks = a.tracks.split(",")
    d0 = datetime.date.fromisoformat(a.frm); d1 = datetime.date.fromisoformat(a.to)
    # 各セル [複勝good, n]
    def z(): return [0, 0]
    base = z(); base_baba = z()
    cells = {k: z() for k in [
        "R父", "R母父", "R父or母父", "R両側二重", "R×道悪",
        "M父", "M母父", "M父or母父", "M×道悪",
        "R or M(父母父)", "(R and M)配合"]}

    day = d0
    while day <= d1:
        ymd = day.strftime("%Y%m%d")
        for tr in tracks:
            try:
                idx = c.get(CARD.format(r=day_index_race_id(ymd, tr)), use_cache=True)
                races = dict(P.parse_race_links(idx, date_yyyymmdd=ymd, jyo_code=ALL_CODES[tr]))
            except Exception:
                races = {}
            for R, rid in sorted(races.items()):
                try:
                    _ch = c.get(CARD.format(r=rid), use_cache=True)
                    pc = P.parse_card_page(_ch, rid)
                    rr = P.parse_result_page(c.get(PERF.format(r=rid), use_cache=True), rid)
                except Exception:
                    continue
                if not rr.rows or not rr.rows[0].finish_pos:
                    continue
                try:
                    from rakuten_ped import attach as _apd
                    _apd(_ch, pc.entries)
                except Exception:
                    pass
                baba = getattr(rr, "baba", None) or getattr(pc, "baba", None) or ""
                wet = any(x in baba for x in BAD)
                emap = {e.umaban: e for e in pc.entries if e.umaban}
                for row in rr.rows:
                    if not (row.umaban and row.finish_pos and row.popularity):
                        continue
                    if row.popularity < a.usui:
                        continue
                    e = emap.get(row.umaban)
                    if not e:
                        continue
                    g = 1 if row.finish_pos <= 3 else 0
                    base[0] += g; base[1] += 1
                    if wet:
                        base_baba[0] += g; base_baba[1] += 1
                    sire = e.sire or ""; ds = getattr(e, "dam_sire", "") or ""
                    Rs, Rd = has(sire, ROBERTO), has(ds, ROBERTO)
                    Ms, Md = has(sire, MRPROSPECTOR), has(ds, MRPROSPECTOR)
                    def add(k):
                        cells[k][0] += g; cells[k][1] += 1
                    if Rs: add("R父")
                    if Rd: add("R母父")
                    if Rs or Rd: add("R父or母父")
                    if Rs and Rd: add("R両側二重")
                    if (Rs or Rd) and wet: add("R×道悪")
                    if Ms: add("M父")
                    if Md: add("M母父")
                    if Ms or Md: add("M父or母父")
                    if (Ms or Md) and wet: add("M×道悪")
                    if Rs or Rd or Ms or Md: add("R or M(父母父)")
                    if (Rs or Rd) and (Ms or Md): add("(R and M)配合")
        day += datetime.timedelta(days=1)

    b = base[0] / base[1] if base[1] else 0
    bw = base_baba[0] / base_baba[1] if base_baba[1] else 0
    print(f"=== 血統収束の全スケール裏取り {a.frm}〜{a.to} ({a.tracks}) 人気薄≥{a.usui} ===")
    print(f" 深さ=父+母父(2代・下限) / 好走=3着内")
    print(f" [ベース] 全体 {b:.1%}({base[0]}/{base[1]}) / 道悪時 {bw:.1%}({base_baba[0]}/{base_baba[1]})")
    print("\n R=ロベルト系(グリップ) / M=ミスプロ系ダートパワー")
    for k, cc in cells.items():
        if not cc[1]:
            print(f" {k:16s} n0"); continue
        bb = bw if "道悪" in k else b
        r = cc[0] / cc[1]
        print(f" {k:16s} {r:5.1%}({cc[0]:>3}/{cc[1]:>4}) lift{(r/bb if bb else 0):4.2f}")


if __name__ == "__main__":
    main()
