#!/bin/bash
# build_shots.sh <subject_json|-> <tag>  — the three shots with a character: scene_template (per shot) →
# build_character.py → make_shot_00N.py → animate_shot_00N.py. Out: /home/claude/shots/<tag>/SHOT_00N_<tag>.blend
set -e
export PATH=/home/claude/bin:$PATH OCIO=/home/claude/vsc/benchmarks/bakeoff/01J7B000000000000000BAKEXP/slice/ocio/studio-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio
SUBJ="$1"; TAG="$2"; K=/home/claude/video-slice-contractor/contractor/contractor-restore-kit/scripts; B=/home/claude/b3; O=/home/claude/shots/$TAG
mkdir -p $O; cd $O
declare -A V=([1]=shot_001_v02 [2]=shot_002_v03 [3]=shot_003_v06)
for n in ${3:-1 2 3}; do
  S=SHOT_00$n
  [ -f /home/claude/shots/template_$S.blend ] || blender -b --python-exit-code 2 -P /home/claude/vsc/slice/scene_template.py -- --out /home/claude/shots/template_$S.blend --shot $S > /dev/null
  if [ "$SUBJ" = "-" ]; then A=""; else A="--subject $SUBJ"; fi
  blender -b /home/claude/shots/template_$S.blend --python-exit-code 2 -P $B/build_character.py -- --out char_$S.blend $A > build_$S.log 2>&1
  blender -b char_$S.blend --python-exit-code 2 -P $K/${V[$n]}/make_shot_00$n.py -- --out ${S}_$TAG.blend > make_$S.log 2>&1
  blender -b ${S}_$TAG.blend --python-exit-code 2 -P $K/${V[$n]}/animate_shot_00$n.py -- --out ${S}_$TAG.blend > anim_$S.log 2>&1
  echo "$S $(tail -1 anim_$S.log | cut -c1-120)"
done
