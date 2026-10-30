import bpy, sys
a = sys.argv[sys.argv.index("--") + 1:]; out, fr = a[0], int(a[1]); x0, x1, y0, y1 = map(float, a[2:6])
sc = bpy.data.scenes["SLICE"]; sc.frame_set(fr)
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 12; sc.render.resolution_percentage = 50
sc.render.use_border = True; sc.render.use_crop_to_border = True
sc.render.border_min_x, sc.render.border_max_x, sc.render.border_min_y, sc.render.border_max_y = x0, x1, y0, y1
sc.render.filepath = out + ".exr"; bpy.ops.render.render(write_still=True)
import glob; img = bpy.data.images.load(sorted(glob.glob(out + ".exr*"))[0])
tmp = bpy.data.scenes.new("PNG_OUT"); tmp.render.image_settings.file_format = "PNG"; tmp.render.image_settings.color_mode = "RGB"
for k in ("view_transform", "look", "exposure", "gamma"): setattr(tmp.view_settings, k, getattr(sc.view_settings, k))
tmp.display_settings.display_device = sc.display_settings.display_device; img.save_render(out, scene=tmp); print("CROP_OK", out)
