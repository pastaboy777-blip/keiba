"""netkeiba の5代血統表を取得し、テシオ理論(自分流)の活性値・優先祖先・基礎体力を算出する。

活性値(自分流): 先祖Aが血統表上の子(生年 Y_foal)を産んだ時の値
    活性値(A) = ((Y_foal - B_A - 2) mod 8) + 1   (B_A=Aの生年, 受胎年=Y_foal-1)
  記事の実例で検証済: サンデーサイレンス7 / Halo8 / Wishing Well2 / ディープ6 / Unbridled's Song8。
  0活性は廃止(8↔1で連続遷移)。

優先祖先(自分流): 父の活性値 A と 母方最強種牡馬の活性値 B の差 = 遡る世代数。
  父優勢(A>=B)なら父系をその世代数だけ遡る / 母優勢なら母方最強種牡馬を採る。
  同値は若い世代を優位。
基礎体力: (1〜4代母の活性値の和 ÷ 32) × 100。50基準・70超でタフ。

血統ページ: https://db.netkeiba.com/horse/ped/<horse_id>/ (EUC-JP, rowspanで世代)
"""

from __future__ import annotations

import re

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore

PED_URL = "https://db.netkeiba.com/horse/ped/{horse_id}/"


def parse_pedigree(html: str) -> dict:
    """血統表を {パス: {name, year, male}} に。パスは S=父系/D=母系 (例 'SS'=父父, 'DDD'=3代母)。"""
    if BeautifulSoup is None:
        raise ImportError("beautifulsoup4 が必要です")
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=re.compile("blood"))
    if table is None:
        return {}
    trs = table.find_all("tr")
    nrows = len(trs) or 32
    occupied: set = set()
    anc: dict = {}
    for r, tr in enumerate(trs):
        col = 0
        for td in tr.find_all("td"):
            while (r, col) in occupied:
                col += 1
            rowspan = int(td.get("rowspan") or 1)
            gen = col + 1
            for rr in range(r, r + rowspan):
                occupied.add((rr, col))
            block = max(1, nrows // (2 ** gen))
            idx = r // block
            bits = format(idx, f"0{gen}b")
            path = "".join("S" if b == "0" else "D" for b in bits)
            a = td.find("a", href=re.compile(r"/horse/\d"))
            name = a.get_text(strip=True) if a else td.get_text(" ", strip=True)[:20]
            ym = re.search(r"(19|20)\d{2}", td.get_text())
            anc[path] = {"name": name, "year": int(ym.group()) if ym else None,
                         "male": path.endswith("S")}  # 末尾S=その代の父=牡
            col += 1
    return anc


def activity(birth_year: int | None, foal_year: int | None):
    """活性値(自分流): ((Y_foal - B - 2) mod 8) + 1。生年欠落は None。"""
    if not birth_year or not foal_year:
        return None
    return ((foal_year - birth_year - 2) % 8) + 1


def analyze(anc: dict, subject_year: int) -> dict:
    """活性値・優先祖先・基礎体力をまとめて算出。"""
    act = {}
    for path, a in anc.items():
        foal_year = subject_year if len(path) == 1 else (anc.get(path[:-1], {}) or {}).get("year")
        act[path] = activity(a["year"], foal_year)

    # 基礎体力: 1〜4代母 = D, DD, DDD, DDDD
    dam_paths = ["D", "DD", "DDD", "DDDD"]
    dam_acts = [(p, act.get(p)) for p in dam_paths]
    vals = [v for _, v in dam_acts if v is not None]
    kiso = round(sum(vals) / 32 * 100, 1) if len(vals) == 4 else None

    # 優先祖先: 父(S)の活性値 A, 母方の牡(最強)の活性値 B
    a_father = act.get("S")
    mat_stallions = [(p, act[p]) for p, a in anc.items()
                     if p.startswith("D") and a["male"] and act.get(p) is not None]
    best_mat = max(mat_stallions, key=lambda x: (x[1], -len(x[0]))) if mat_stallions else None

    yusen = None
    if a_father is not None and best_mat is not None:
        b_path, b_act = best_mat
        diff = abs(a_father - b_act)
        if a_father >= b_act:
            # 父系を diff 世代遡る (父=1世代目)。diff=0なら父。
            p = "S" * max(1, diff)
            while p and p not in anc:
                p = p[:-1]  # 深すぎる場合は手前に丸める
            yusen = {"path": p, "name": anc.get(p, {}).get("name"),
                     "activity": act.get(p), "side": "父系", "diff": diff}
        else:
            yusen = {"path": b_path, "name": anc[b_path]["name"],
                     "activity": b_act, "side": "母系(最強種牡馬)", "diff": diff}

    return {"activity": act, "kiso_tairyoku": kiso, "dam_acts": dam_acts,
            "yusen_sosen": yusen, "father_act": a_father,
            "best_maternal": best_mat}
