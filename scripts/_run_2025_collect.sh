#!/usr/bin/env bash
set -u
cd /home/user/keiba
for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
  # 月末日
  case $m in 01|03|05|07|08|10|12) last=31;; 04|06|09|11) last=30;; 02) last=28;; esac
  out="data/samples/nankan_2025-$m.jsonl"
  echo "===== 2025-$m START $(date -u +%H:%M:%S) ====="
  python3 scripts/collect_nankan.py --start 2025-$m-01 --end 2025-$m-$last --all --out "$out" 2>&1
  echo "===== 2025-$m DONE lines=$(wc -l < "$out" 2>/dev/null) $(date -u +%H:%M:%S) ====="
done
echo "ALL DONE $(date -u +%H:%M:%S)"
