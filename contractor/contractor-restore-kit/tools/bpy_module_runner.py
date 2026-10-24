"""Emulates `blender -b <blend> -P <script> -- <args>` with the bpy module. Usage: runbl.py <script> <blend|-> [args]"""
import sys, runpy, bpy
script, blend = sys.argv[1], sys.argv[2]
rest = sys.argv[3:]
if blend != "-":
    bpy.ops.wm.open_mainfile(filepath=blend)
sys.argv = [script] + (["--"] + rest if rest else [])
runpy.run_path(script, run_name="__main__")
