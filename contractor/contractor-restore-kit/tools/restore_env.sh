#!/bin/bash
# Rebuild the contractor's working environment in a fresh claude.ai sandbox (no Blender binary, no GPU).
# ~1 minute. Blender 5.2.1 runs as the PyPI module `bpy`; scripts are run through bpy_module_runner.py,
# which emulates `blender -b <file> -P <script> -- <args>`.
set -e
cd /home/claude
which uv >/dev/null 2>&1 || pip install -q uv --break-system-packages
uv venv -q --python 3.13 bpyenv
uv pip install -q --python ./bpyenv/bin/python bpy==5.2.1 numpy pillow OpenImageIO jsonschema referencing
[ -d vsc ] || git clone -q https://github.com/artemzhzhenov/video-slice-contractor.git vsc
(cd vsc && git pull -q)
./bpyenv/bin/python -c "import bpy; print('bpy', bpy.app.version_string)"
echo 'export OCIO=/home/claude/vsc/benchmarks/bakeoff/01J7B000000000000000BAKEXP/slice/ocio/studio-config-v4.0.0_aces-v2.0_ocio-v2.5.ocio'
echo 'run:  /home/claude/bpyenv/bin/python bpy_module_runner.py <script.py> <file.blend|-> [args]'
# MPFB2 (only needed to rebuild the CHARACTER from build_character.py; shot edits run on the accepted .blend):
#   git clone --branch v2.0.17 https://github.com/makehumancommunity/mpfb2.git && (cd mpfb2/src && zip -qr mpfb.zip mpfb)
#   install mpfb.zip as a Blender extension in repo user_default (see burst-1 REPORT.md, step 0)
