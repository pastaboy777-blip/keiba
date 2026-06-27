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
            hm = re.search(r"/horse/(\d+)", a["href"]) if a else None
            ym = re.search(r"(19|20)\d{2}", td.get_text())
            anc[path] = {"name": name, "year": int(ym.group()) if ym else None,
                         "id": hm.group(1) if hm else None,
                         "male": path.endswith("S")}  # 末尾S=その代の父=牡
            col += 1
    return anc


def activity(birth_year: int | None, foal_year: int | None):
    """活性値(自分流): ((Y_foal - B - 2) mod 8) + 1。生年欠落は None。"""
    if not birth_year or not foal_year:
        return None
    return ((foal_year - birth_year - 2) % 8) + 1


def inbreeding(anc: dict, act: dict) -> list[dict]:
    """クロス(同一先祖の重複)を検出し、影響度を算出する(自分流テシオ)。

    ルール: 若い世代のクロスほど影響大・古いほど小(0活性廃止=1世代では消えない)。
    影響度 = Σ_ペア (1/2)^(g_i+g_j-1) (Wright流。世代が近いほど指数的に大)。
    クロス=悪とはせず、各出現の活性値も併記(活性で強弱・良悪は別の話)。
    同一馬判定は horse_id 優先(無ければ馬名)。
    """
    groups: dict = {}
    for path, a in anc.items():
        if not path or not a.get("name"):
            continue
        key = a["name"].strip()          # 馬名で同一馬判定(同名セルは完全一致)
        groups.setdefault(key, []).append(path)
    out = []
    for key, paths in groups.items():
        if len(paths) < 2:
            continue
        gens = sorted(len(p) for p in paths)
        strength = 0.0
        for i in range(len(gens)):
            for j in range(i + 1, len(gens)):
                strength += 0.5 ** (gens[i] + gens[j] - 1)
        acts = [act.get(p) for p in paths]
        out.append({
            "name": anc[paths[0]]["name"],
            "gens": gens,                       # 例 [4,5] = 4×5
            "cross": "×".join(map(str, gens)),
            "strength": round(strength, 4),
            "activities": acts,
            "paths": paths,
        })
    out.sort(key=lambda x: -x["strength"])
    return out


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

    # 優先祖先: 父(S)の活性値 A vs 母系サイアーライン(母父DS・母母父DDS…)の最強 B。
    # ※母方“最強種牡馬”は母系の底辺サイアー(D*k+S)に限定する(記事の例で確認:
    #   ディープ=Busted(DDS,5)を採用しCrepello(DDSS,8)は除外 → 優先祖先Haloに一致)。
    a_father = act.get("S")
    bottom_sires = []
    for k in range(1, 5):                    # DS, DDS, DDDS, DDDDS
        p = "D" * k + "S"
        if p in anc and act.get(p) is not None:
            bottom_sires.append((p, act[p]))
    # 同活性は若い世代(短いパス=近い)を優位
    best_mat = max(bottom_sires, key=lambda x: (x[1], -len(x[0]))) if bottom_sires else None

    yusen = None
    if a_father is not None and best_mat is not None:
        b_path, b_act = best_mat
        diff = abs(a_father - b_act)
        if a_father >= b_act:
            # 父優勢: 父系を diff 世代遡る(父=1世代目)。diff<=1は父。
            p = "S" * max(1, diff)
            while p and p not in anc:
                p = p[:-1]
            yusen = {"path": p, "name": anc.get(p, {}).get("name"),
                     "activity": act.get(p), "side": "父系", "diff": diff}
        else:
            # 母優勢: 母系サイアーラインの最強種牡馬を優先祖先とする
            yusen = {"path": b_path, "name": anc[b_path]["name"],
                     "activity": b_act, "side": "母系サイアーライン", "diff": diff}

    return {"activity": act, "kiso_tairyoku": kiso, "dam_acts": dam_acts,
            "yusen_sosen": yusen, "father_act": a_father,
            "best_maternal": best_mat, "inbreeding": inbreeding(anc, act)}
