#!/bin/bash
export PATH=/home/claude/bin:$PATH OCIO=/home/claude/vsc/benchmarks/bakeoff/01J7B000000000000000BAKEXP/slice/ocio/studio-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio
Q=/home/claude/shots/pair89; mkdir -p $Q; cd $Q
for t in s08 s09; do for n in 1 2 3; do [ -f clear_${t}_$n.done ] && continue; X=""; [ $n = 1 ] && X="--extremes"
  s=$(date +%s); blender -b /home/claude/shots/$t/SHOT_00${n}_$t.blend --python-exit-code 2 -P /home/claude/vsc/slice/measurements/accessory_clearance.py -- --out clear_${t}_SHOT_00$n.json $X > clear_${t}_$n.log 2>&1
  echo "clear $t SHOT_00$n rc=$? t=$(( $(date +%s)-s ))" >> queue.log; touch clear_${t}_$n.done; done; done
for t in s08 s09; do for n in 1 2 3; do [ -f mouth_${t}_$n.done ] && continue
  s=$(date +%s); blender -b /home/claude/shots/$t/SHOT_00${n}_$t.blend --python-exit-code 2 -P /home/claude/vsc/slice/measurements/mouth_check.py -- --out mouth_${t}_SHOT_00$n.json > mouth_${t}_$n.log 2>&1
  echo "mouth $t SHOT_00$n rc=$? t=$(( $(date +%s)-s )) $(grep -oE 'MOUTH_(OK|FAIL)' mouth_${t}_$n.log | head -1)" >> queue.log; touch mouth_${t}_$n.done; done; done
for t in s08 s09; do for n in 1 2 3; do [ -f quick_${t}_$n.done ] && continue; rm -rf quick_${t}_SHOT_00$n
  s=$(date +%s); (cd /home/claude/vsc && CHECK_ASSET_QUICK=1 slice/check_asset.sh /home/claude/shots/$t/SHOT_00${n}_$t.blend $Q/quick_${t}_SHOT_00$n 64 25 SHOT_00$n) > quick_${t}_$n.log 2>&1
  echo "quick $t SHOT_00$n rc=$? t=$(( $(date +%s)-s ))" >> queue.log; touch quick_${t}_$n.done; done; done
echo QUEUE_DONE >> queue.log
