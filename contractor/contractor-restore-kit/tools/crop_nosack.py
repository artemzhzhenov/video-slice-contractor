import bpy
o = bpy.data.objects.get("HERO_MOUTH_SACK")
if o: o.hide_render = True
exec(open("/tmp/crop.py").read())
