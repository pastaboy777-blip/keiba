#!/bin/bash
# 南関4場のnetkeibaキャッシュを期間指定で作る。
#   netkeiba NAR race_id = 2026 + 場(2) + MMDD + RR   （42浦和 43船橋 44大井 45川崎）
# 各(場,日)でまず1Rを引き、開催が無ければその日はスキップする。
#   使い方: build_nkcache.sh 2026 0101 0802
CACHE=${NKCACHE:-/tmp/claude-0/-home-user-keiba/5c9e9520-78d2-57a1-98df-28a0a517ec92/scratchpad/nkcache}
YEAR=${1:-2026}; FROM=${2:-0101}; TO=${3:-0802}
mkdir -p "$CACHE"
ok=0
for MMDD in $(python3 -c "
import datetime,sys
y,a,b=int('$YEAR'),'$FROM','$TO'
d=datetime.date(y,int(a[:2]),int(a[2:])); e=datetime.date(y,int(b[:2]),int(b[2:]))
while d<=e:
    print(d.strftime('%m%d')); d+=datetime.timedelta(days=1)
"); do
  for PL in 42 43 44 45; do
    F="$CACHE/${YEAR}${PL}${MMDD}01.html"
    if [ ! -s "$F" ] || [ $(stat -c%s "$F") -lt 20000 ]; then
      curl -s -L --max-time 20 "https://db.netkeiba.com/race/${YEAR}${PL}${MMDD}01/" -o "$F"
    fi
    [ -s "$F" ] && [ $(stat -c%s "$F") -ge 20000 ] || continue
    for RR in 02 03 04 05 06 07 08 09 10 11 12; do
      G="$CACHE/${YEAR}${PL}${MMDD}${RR}.html"
      [ -s "$G" ] && [ $(stat -c%s "$G") -ge 20000 ] && continue
      curl -s -L --max-time 20 "https://db.netkeiba.com/race/${YEAR}${PL}${MMDD}${RR}/" -o "$G" &
    done
    wait
    ok=$((ok+1)); echo "取得 ${YEAR}${PL}${MMDD}"
  done
done
echo "DONE 開催日×場= $ok"
