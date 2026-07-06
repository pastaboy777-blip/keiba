#!/usr/bin/env bash
set -u
cd /home/user/keiba
MONTHS="2024-07 2024-08 2024-09 2024-10 2024-11 2024-12 2025-01 2025-02 2025-03 2025-04 2025-05 2025-06"
for M in $MONTHS; do
  Y=${M%-*}; MM=${M#*-}
  END=$(python3 -c "import calendar; print(f'{$Y}-{$((10#$MM)):02d}-{calendar.monthrange($Y,$((10#$MM)))[1]:02d}')")
  OUT="data/samples/kochi_${M}.jsonl"
  echo "=== collecting $M (${M}-01 .. $END) -> $OUT ==="
  rm -f "$OUT"
  python3 scripts/collect_local.py --start "${M}-01" --end "$END" --place 高知 --out "$OUT" 2>&1
  if [ -s "$OUT" ]; then
    N=$(wc -l < "$OUT")
    git add "$OUT"
    git -c user.email=noreply@anthropic.com -c user.name=Claude commit -q -m "高知データ収集(2年目): ${M} (${N}レース)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GHMR1jW5c3gNMRMgf1XYdG"
    echo "=== committed $M: $N races ==="
  else
    echo "=== $M: no races, skip ==="; rm -f "$OUT"
  fi
done
echo "=== KOCHI Y2 ALL DONE ==="
