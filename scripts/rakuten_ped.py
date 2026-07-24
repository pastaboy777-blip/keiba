#!/usr/bin/env python3
"""楽天出馬表(race_card)のセルから 父・母父 をインライン抽出する。
セル形式： "父名 馬名 母名 (母父名) オッズ （人気） 生年月日 …"
 ・母父は"馬名より後の最初の半角カッコ (…) "(人気は全角（）・着差は数字なので除外)。
 ・父は"馬名の直前トークン"。
本人指摘(2026-07-24)：このリポのparser.pyがdam_sireに拾えていなかった＝母父は楽天カードに在る。"""
import re
from bs4 import BeautifulSoup


def _sire_from(pt, name):
    i = pt.find(name)
    if i < 0:
        return None
    toks = pt[:i].strip().split()
    return toks[-1] if toks else None


def _dam_from(pt, name):
    i = pt.find(name)
    after = pt[i + len(name):] if i >= 0 else pt
    for m in re.finditer(r'\(([^)]{2,20})\)', after):    # 半角カッコのみ(全角の人気は除外)
        v = m.group(1).strip()
        if re.match(r'[ァ-ヶA-Za-z’\'’]', v) and not re.match(r'^[\d\.\s]+$', v):
            return v
    return None


def attach(card_html, entries):
    """entries(各 e に umaban/horse_name)に e.sire_kb / e.dam_sire を付与して返す。
    e.dam_sire を上書き設定(空なら埋める)。"""
    s = BeautifulSoup(card_html, "html.parser")
    cells = {}
    for a in s.find_all("a"):
        nm = a.get_text(" ", strip=True)
        par = a.find_parent(["td", "th", "div"])
        if not (par and nm):
            continue
        pt = re.sub(r"\s+", " ", par.get_text(" ", strip=True))
        if "（" in pt and "(" in pt and 3 <= len(nm) <= 12:   # 血統セルらしい
            cells.setdefault(nm, pt)
    for e in entries:
        nm = getattr(e, "horse_name", None)
        if not nm or nm not in cells:
            continue
        pt = cells[nm]
        dam = _dam_from(pt, nm)
        sire = _sire_from(pt, nm)
        if dam:
            try:
                e.dam_sire = dam
            except Exception:
                pass
        if sire and not getattr(e, "sire", None):
            try:
                e.sire = sire
            except Exception:
                pass
    return entries
