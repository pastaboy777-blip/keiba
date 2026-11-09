#!/bin/bash
# 楽天の出馬表から 馬名→父 を集める。siremap.json の網羅率を上げる。
#   RACEID = YYYYMMDD + 場(2) + 1506 + 開催日(2) + RR   （18浦和 19船橋 20大井 21川崎）
OUT=${SIREDIR:-/tmp/claude-0/-home-user-keiba/5c9e9520-78d2-57a1-98df-28a0a517ec92/scratchpad/cards}
mkdir -p "$OUT"
python3 - <<'PY' > /tmp/_days.txt
import sys; sys.path.insert(0,'scripts/ana')
import bt
C={"浦和":"18","船橋":"19","大井":"20","川崎":"21"}
seen=set()
for r in bt.load("2026-01-01","2026-12-31"):
    seen.add((r["date"].replace("-",""), C[r["place"]], f"{r['rn']:02d}"))
for d,p,rn in sorted(seen): print(d,p,rn)
PY
n=0
while read D P RR; do
  F="$OUT/${D}${P}${RR}.html"
  [ -s "$F" ] && [ $(stat -c%s "$F") -gt 40000 ] && continue
  curl -s -L --max-time 20 "https://keiba.rakuten.co.jp/race_card/list/RACEID/${D}${P}150601${RR}" -o "$F" &
  n=$((n+1)); [ $((n % 8)) -eq 0 ] && wait
done < /tmp/_days.txt
wait
echo "DONE $(ls $OUT | wc -l) ファイル"
