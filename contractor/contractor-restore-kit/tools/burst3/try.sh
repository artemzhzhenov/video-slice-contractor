#!/bin/bash
# try.sh TAG WRAP_DEG UPPER_BACK [SHOTS]  — build 01 on the shot templates with the given sack wrap / upper set-back, mouth_check each shot
export PATH=/home/claude/bin:$PATH OCIO=/home/claude/vsc/benchmarks/bakeoff/01J7B000000000000000BAKEXP/slice/ocio/studio-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio
T=$1; W=$2; U=$3; SH=${4:-"1 2"}; D=/home/claude/teeth/try/$T; mkdir -p $D; cd $D
K=/home/claude/video-slice-contractor/contractor/contractor-restore-kit/scripts
declare -A V=([1]=shot_001_v02 [2]=shot_002_v03 [3]=shot_003_v06)
for n in $SH; do
  MOUTH_SACK_WRAP_DEG=$W UPPER_TEETH_BACK_M=$U blender -b /home/claude/shots/template_SHOT_00$n.blend --python-exit-code 2 -P /home/claude/b3/build_character.py -- --out c$n.blend --subject /home/claude/b3/subject_01.json > b$n.log 2>&1
  blender -b c$n.blend --python-exit-code 2 -P $K/${V[$n]}/make_shot_00$n.py -- --out s$n.blend > /dev/null 2>&1
  blender -b s$n.blend --python-exit-code 2 -P $K/${V[$n]}/animate_shot_00$n.py -- --out s$n.blend > /dev/null 2>&1
  blender -b s$n.blend --python-exit-code 2 -P /home/claude/vsc/slice/measurements/mouth_check.py -- --out m$n.json > m$n.log 2>&1
  echo "$T SHOT_00$n: $(grep -oE 'MOUTH_(OK|FAIL)[^(]{0,150}' m$n.log | head -1)"
done
