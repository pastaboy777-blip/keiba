#!/bin/bash
# 南関キャッシュを7/5〜8/1まで延長。netkeiba NAR race_id = 2026 + 場(2) + MMDD + RR
CACHE=/tmp/claude-0/-home-user-keiba/5c9e9520-78d2-57a1-98df-28a0a517ec92/scratchpad/nkcache
for MMDD in 0705 0706 0707 0708 0709 0710 0711 0712 0713 0714 0715 0716 0717 0718 0719 0720 0721 0722 0723 0724 0725 0726 0727 0728 0729 0730 0731 0801; do
  for PL in 42 43 44 45; do
    F="$CACHE/2026${PL}${MMDD}01.html"
    if [ ! -s "$F" ] || [ $(stat -c%s "$F") -lt 20000 ]; then
      curl -s -L --max-time 20 "https://db.netkeiba.com/race/2026${PL}${MMDD}01/" -o "$F"
    fi
    if [ -s "$F" ] && [ $(stat -c%s "$F") -ge 20000 ]; then
      for RR in 02 03 04 05 06 07 08 09 10 11 12; do
        G="$CACHE/2026${PL}${MMDD}${RR}.html"
        [ -s "$G" ] && [ $(stat -c%s "$G") -ge 20000 ] && continue
        curl -s -L --max-time 20 "https://db.netkeiba.com/race/2026${PL}${MMDD}${RR}/" -o "$G" &
      done
      wait
      echo "取得 2026${PL}${MMDD}"
    fi
  done
done
echo DONE
