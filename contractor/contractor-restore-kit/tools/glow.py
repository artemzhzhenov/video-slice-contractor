import bpy
def emit(name, col):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
    for n in list(nt.nodes): nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission"); e.inputs[0].default_value = col; e.inputs[1].default_value = 6
    o = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(e.outputs[0], o.inputs[0]); return m
g = emit("G", (0, 1, 0, 1)); r = emit("R", (1, 0, 0, 1)); b = emit("B", (0, 0.3, 1, 1))
for n, m in (("HERO_TEETH_UPPER", g), ("HERO_TEETH_LOWER", g), ("HERO_TONGUE", b), ("HERO_MOUTH_SACK", r)):
    for s in bpy.data.objects[n].material_slots: s.material = m
exec(open("/tmp/crop.py").read())
