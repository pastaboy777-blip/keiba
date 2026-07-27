"""`data/` 以下のファイルを、カレントディレクトリに依存せず解決する。

⚠️ 相対パス `Path("data/par_pace.json")` のままだと、リポジトリ直下以外から
実行したときに**黙ってフォールバックへ落ちる**。実際 2026-07-27 の川崎で、
別ディレクトリに置いたスクリプトから呼んだせいで `par_win.json` が読まれず、
当日の馬場差が誤った基準（全出走馬par）で計算され続けていた。
例外も警告も出ないので気づきにくい。**必ずこの関数を通すこと。**

探索順:
  1. 環境変数 NANKEIBA_DATA
  2. カレントディレクトリ（リポジトリ直下から動かした場合）
  3. パッケージから見たリポジトリ直下（src/nankeiba/core/ の3つ上）
"""

from __future__ import annotations

import os
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[3]      # …/src/nankeiba/core → repo


def data_path(name: str) -> Path:
    """`data/<name>` の実在するパスを返す。無ければ最後の候補を返す。"""
    cands = []
    env = os.environ.get("NANKEIBA_DATA")
    if env:
        cands.append(Path(env) / name)
    cands.append(Path("data") / name)
    cands.append(_PKG_ROOT / "data" / name)
    for p in cands:
        if p.exists():
            return p
    return cands[-1]
