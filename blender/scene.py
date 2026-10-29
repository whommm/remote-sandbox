# -*- coding: utf-8 -*-
"""
Rainy-night konbini street corner — Blender (bpy) scene builder.
Run:  blender -b -P scene.py -- --out /path/render.png --res 1200 800 --samples 96
Compatible with Blender 3.4 ~ 4.x (cycles CPU).
"""
import bpy, bmesh, math, random, sys, os
from mathutils import Vector, Euler

argv = sys.argv
argv = argv[argv.index('--') + 1:] if '--' in argv else []

def arg(name, default):
    if name in argv:
        return argv[argv.index(name) + 1]
    return default

OUT = arg('--out', '/tmp/konbini_blender.png')
RES = (int(arg('--resx', 1200)), int(arg('--resy', 800)))
SAMPLES = int(arg('--samples', 96))
PREVIEW = '--preview' in argv

random.seed(7)

# ----------------------------------------------------------------------------- reset
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH' if '--workbench' in argv else 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = SAMPLES
DENOISE = arg('--denoise', 'auto')
if DENOISE != 'off':
    scene.cycles.use_denoising = True
    ok = False
    for dn in (('OPENIMAGEDENOISE', 'NLM') if DENOISE == 'auto' else (DENOISE.upper(),)):
        try:
            scene.cycles.denoiser = dn
            ok = True
            break
        except Exception:
            continue
    if not ok:
        scene.cycles.use_denoising = False
else:
    scene.cycles.use_denoising = False
scene.render.resolution_x = RES[0]
scene.render.resolution_y = RES[1]
scene.render.resolution_percentage = 100
scene.render.film_transparent = False
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.filepath = OUT

# color management
try:
    scene.view_settings.view_transform = 'AgX'
except Exception:
    try:
        scene.view_settings.view_transform = 'Filmic'
    except Exception:
        pass
scene.view_settings.look = 'None'
scene.view_settings.exposure = 0.0

scene.cycles.max_bounces = 6
scene.cycles.diffuse_bounces = 3
scene.cycles.glossy_bounces = 3
scene.cycles.transmission_bounces = 4
scene.cycles.transparent_max_bounces = 8
scene.cycles.caustics_reflective = False
scene.cycles.caustics_refractive = False

# ----------------------------------------------------------------------------- helpers
def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get('Principled BSDF')
    return m, nt, bsdf

def setin(node, names, value):
    """set a Principled input by trying several possible socket names."""
    for n in names:
        if n in node.inputs:
            node.inputs[n].default_value = value
            return True
    return False

def mat(name, color, rough=0.55, metal=0.0, emit=None, emit_str=0.0, alpha=1.0,
        transmission=0.0, ior=1.45, spec=0.35):
    m, nt, b = new_mat(name)
    setin(b, ['Base Color'], (color[0], color[1], color[2], 1.0))
    setin(b, ['Roughness'], rough)
    setin(b, ['Metallic'], metal)
    setin(b, ['IOR'], ior)
    setin(b, ['Specular', 'Specular IOR Level'], spec)
    if transmission > 0:
        setin(b, ['Transmission', 'Transmission Weight'], transmission)
    if alpha < 1.0:
        setin(b, ['Alpha'], alpha)
        m.blend_method = 'BLEND'
        try:
            m.shadow_method = 'NONE'
        except Exception:
            pass
    if emit is not None and emit_str > 0:
        setin(b, ['Emission Color', 'Emission'], (emit[0], emit[1], emit[2], 1.0))
        setin(b, ['Emission Strength'], emit_str)
    return m

def obj_mesh(name, verts, faces, material=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    if material:
        ob.data.materials.append(material)
    return ob

def box(name, size, loc, material, rot=(0, 0, 0)):
    sx, sy, sz = size[0] / 2, size[1] / 2, size[2] / 2
    v = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
         (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]
    f = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    ob = obj_mesh(name, v, f, material)
    ob.location = loc
    ob.rotation_euler = Euler(rot)
    return ob

def cyl(name, r, h, loc, material, segs=20, rot=(0, 0, 0), r2=None):
    bm = bmesh.new()
    if r2 is None:
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs,
                              radius1=r, radius2=r, depth=h)
    else:
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs,
                              radius1=r, radius2=r2, depth=h)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(material)
    ob.location = loc
    ob.rotation_euler = Euler(rot)
    return ob

def sphere(name, r, loc, material, segs=16):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=max(6, segs // 2), radius=r)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(material)
    ob.location = loc
    return ob

def tube(name, p0, p1, r, material, segs=10):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    h = d.length
    ob = cyl(name, r, h, (p0 + p1) / 2, material, segs)
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = d.to_track_quat('Z', 'Y')
    return ob

def poly_curve(name, points, r, material):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = r
    cu.bevel_resolution = 2
    sp = cu.splines.new('POLY')
    sp.points.add(len(points) - 1)
    for i, p in enumerate(points):
        sp.points[i].co = (p[0], p[1], p[2], 1)
    ob = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(material)
    return ob

def smooth(ob):
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob

def area_light(name, loc, size, energy, color, rot=(0, 0, 0), shape='SQUARE', size_y=None):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy
    ld.color = color
    ld.shape = shape
    ld.size = size
    if size_y is not None and shape == 'RECTANGLE':
        ld.size_y = size_y
    ob = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = Euler(rot)
    return ob

def point_light(name, loc, energy, color, radius=0.1):
    ld = bpy.data.lights.new(name, 'POINT')
    ld.energy = energy
    ld.color = color
    ld.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    return ob

def spot_light(name, loc, target, energy, color, angle=0.9, blend=0.5, radius=0.15):
    ld = bpy.data.lights.new(name, 'SPOT')
    ld.energy = energy
    ld.color = color
    ld.spot_size = angle
    ld.spot_blend = blend
    ld.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return ob

def text_obj(name, body, size, loc, material, rot=(math.pi / 2, 0, 0), extrude=0.006, align='CENTER'):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.align_y = 'CENTER'
    cu.extrude = extrude
    font_path = None
    for p in ('/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf',
              '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf',
              '/usr/share/fonts/truetype/ipafont-gothic/ipag.ttf'):
        if os.path.exists(p):
            font_path = p
            break
    if font_path:
        try:
            cu.font = bpy.data.fonts.load(font_path, check_existing=True)
        except Exception:
            pass
    ob = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(material)
    ob.location = loc
    ob.rotation_euler = Euler(rot)
    return ob

# ----------------------------------------------------------------------------- world
world = bpy.data.worlds.new('World')
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs[0].default_value = (0.008, 0.012, 0.026, 1)
bg.inputs[1].default_value = 0.35

# ----------------------------------------------------------------------------- palette
M_asphalt   = mat('asphalt', (0.045, 0.048, 0.058), rough=0.30, metal=0.0, spec=0.5)
M_wet       = mat('wet', (0.020, 0.022, 0.030), rough=0.045, metal=0.0, spec=0.9)
M_walk      = mat('walk', (0.20, 0.205, 0.22), rough=0.42, metal=0.0, spec=0.5)
M_curb      = mat('curb', (0.34, 0.35, 0.37), rough=0.55)
M_paint     = mat('paint', (0.80, 0.82, 0.85), rough=0.25, spec=0.6)
M_wall      = mat('wall', (0.80, 0.78, 0.72), rough=0.62)
M_wall2     = mat('wall2', (0.62, 0.60, 0.55), rough=0.66)
M_alu       = mat('alu', (0.42, 0.44, 0.47), rough=0.32, metal=0.85)
M_dark      = mat('dark', (0.055, 0.06, 0.07), rough=0.45, metal=0.5)
M_pole      = mat('pole', (0.24, 0.24, 0.26), rough=0.55, metal=0.3)
M_roof      = mat('roof', (0.09, 0.10, 0.12), rough=0.60)
M_floor     = mat('floor_in', (0.50, 0.47, 0.40), rough=0.35)
M_shelf     = mat('shelf', (0.52, 0.52, 0.50), rough=0.5)
M_signface  = mat('signface', (0.95, 0.92, 0.84), rough=0.35, emit=(1.0, 0.93, 0.78), emit_str=0.45)
M_mint      = mat('mint', (0.10, 0.55, 0.50), rough=0.45)
M_coral     = mat('coral', (0.85, 0.38, 0.14), rough=0.45)
M_glass     = mat('glass', (0.90, 0.95, 1.0), rough=0.02, transmission=1.0, alpha=1.0, ior=1.02, spec=0.5)
M_ceillamp  = mat('ceillamp', (1.0, 0.96, 0.88), rough=0.5, emit=(1.0, 0.90, 0.72), emit_str=15.0)
M_fridge    = mat('fridge', (0.85, 0.95, 1.0), rough=0.5, emit=(0.70, 0.90, 1.0), emit_str=14.0)
M_neon_pink = mat('neon_pink', (1.0, 0.35, 0.65), rough=0.5, emit=(1.0, 0.25, 0.60), emit_str=12.0)
M_neon_cyan = mat('neon_cyan', (0.45, 0.9, 1.0), rough=0.5, emit=(0.35, 0.85, 1.0), emit_str=8.0)
M_warm_lamp = mat('warmbulb', (1.0, 0.85, 0.6), rough=0.4, emit=(1.0, 0.78, 0.45), emit_str=18.0)
M_red_light = mat('redlight', (1.0, 0.2, 0.2), rough=0.4, emit=(1.0, 0.15, 0.15), emit_str=10.0)
M_green     = mat('greenlight', (0.2, 1.0, 0.5), rough=0.4, emit=(0.15, 1.0, 0.45), emit_str=10.0)
M_rain      = mat('rain', (0.7, 0.8, 1.0), rough=0.5, emit=(0.55, 0.68, 0.85), emit_str=0.5, alpha=0.35)

PROD_COLORS = [(0.62, 0.06, 0.05), (0.78, 0.36, 0.03), (0.82, 0.62, 0.06), (0.14, 0.42, 0.10),
               (0.04, 0.30, 0.62), (0.12, 0.16, 0.55), (0.45, 0.10, 0.50), (0.78, 0.16, 0.32),
               (0.85, 0.82, 0.72), (0.42, 0.40, 0.34), (0.32, 0.18, 0.08), (0.04, 0.36, 0.30)]
PROD_MATS = [mat('prod%d' % i, c, rough=0.55, spec=0.25) for i, c in enumerate(PROD_COLORS)]

# ----------------------------------------------------------------------------- base
box('plinth', (13.6, 0.7, 13.6), (0, -0.35, 0), M_dark)
box('plinth_rim', (13.9, 0.12, 13.9), (0, -0.72, 0), M_wall2)
box('ground', (13.0, 0.04, 13.0), (0, -0.02, 0), M_asphalt)

# sidewalks
box('sw_front', (7.9, 0.15, 1.50), (-2.45, 0.075, 1.30), M_walk)
box('sw_right', (1.55, 0.15, 8.50), (0.675, 0.075, -3.70), M_walk)
box('sw_far', (7.9, 0.15, 0.80), (-2.45, 0.075, 4.75), M_walk)
box('sw_far_r', (0.80, 0.15, 10.85), (4.30, 0.075, -0.10), M_walk)
box('alley', (0.95, 0.12, 7.0), (-5.975, 0.06, -3.0), M_walk)
# curbs
box('curb1', (7.9, 0.19, 0.10), (-2.45, 0.095, 2.06), M_curb)
box('curb2', (0.10, 0.19, 8.50), (1.44, 0.095, -3.70), M_curb)
box('curb3', (7.9, 0.19, 0.10), (-2.45, 0.095, 4.34), M_curb)
box('curb4', (0.10, 0.19, 10.85), (3.94, 0.095, -0.10), M_curb)

# road paint
for i in range(5):
    box('xw1_%d' % i, (2.3, 0.012, 0.34), (0.55, 0.012, 2.42 + i * 0.62), M_paint)
for i in range(5):
    box('xw2_%d' % i, (0.34, 0.012, 2.1), (1.92 + i * 0.62, 0.012, 1.30), M_paint)
for i in range(5):
    box('lane_%d' % i, (0.9, 0.012, 0.16), (-5.6 + i * 1.9, 0.012, 3.20), M_paint)
for i in range(6):
    box('lane2_%d' % i, (0.16, 0.012, 0.9), (2.68, 0.012, -5.9 + i * 1.55), M_paint)
# parking bay
box('bay_a', (3.4, 0.012, 0.12), (-3.10, 0.012, 2.16), M_paint)
box('bay_b', (3.4, 0.012, 0.12), (-3.10, 0.012, 4.24), M_paint)
box('bay_c', (0.12, 0.012, 2.1), (-4.78, 0.012, 3.20), M_paint)
box('bay_d', (0.12, 0.012, 2.1), (-1.42, 0.012, 3.20), M_paint)

# puddles
for i, (px, pz, pr) in enumerate([(0.5, 1.35, 0.62), (-2.6, 1.15, 0.55), (-5.0, 1.6, 0.35),
                                 (2.7, 3.1, 0.8), (1.0, 3.6, 0.55), (3.3, -1.4, 0.6), (-1.2, 3.9, 0.65)]):
    bm = bmesh.new()
    n = 16
    verts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        rr = pr * (0.75 + 0.25 * math.sin(a * 3.1 + i) + 0.12 * math.sin(a * 5.3))
        verts.append((math.cos(a) * rr, 0.0, math.sin(a) * rr * 0.75))
    for v in verts:
        bm.verts.new(v)
    bm.verts.ensure_lookup_table()
    bm.faces.new(bm.verts)
    me = bpy.data.meshes.new('puddle%d' % i)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new('puddle%d' % i, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(M_wet)
    y = 0.02 if (pz > 2.06) else 0.16
    ob.location = (px, y, pz)

# ----------------------------------------------------------------------------- store shell
SX0, SX1, SZ0, SZ1 = -5.5, -0.15, -6.1, 0.55
H = 3.2
cx, cz = (SX0 + SX1) / 2, (SZ0 + SZ1) / 2
box('store_back', (SX1 - SX0, H, 0.16), (cx, H / 2, SZ0 + 0.08), M_wall)
box('store_left', (0.16, H, SZ1 - SZ0), (SX0 + 0.08, H / 2, cz), M_wall)
box('store_right_solid', (0.16, H, 1.6), (SX1 - 0.08, H / 2, -5.30), M_wall)
box('store_right_band', (0.16, 0.92, 4.86), (SX1 - 0.08, 2.76, -2.07), M_wall)
box('store_front_post', (0.20, H, 0.16), (SX1 - 0.10, H / 2, SZ1 - 0.08), M_wall)
box('store_front_band', (4.0, 0.92, 0.16), (-3.45, 2.76, SZ1 - 0.08), M_wall)
box('store_roof', (5.95, 0.18, 6.9), (cx + 0.06, 3.25, cz - 0.06), M_roof)
box('parapet_f', (5.95, 0.16, 0.12), (cx + 0.06, 3.42, SZ1 + 0.19), M_wall2)
box('parapet_r', (0.12, 0.16, 6.9), (SX1 + 0.24, 3.42, cz - 0.06), M_wall2)
# kick plates
box('kick_f', (4.1, 0.2, 0.12), (-3.4, 0.10, SZ1 - 0.06), M_alu)
box('kick_r', (0.12, 0.2, 4.86), (SX1 - 0.06, 0.10, -2.07), M_alu)

# glass panes (front + right)
for i in range(3):
    x0 = -5.42 + i * 1.32
    box('glass_f%d' % i, (1.32 - 0.08, 2.04, 0.02), (x0 + 0.66, 0.16 + 1.08, SZ1 - 0.075), M_glass)
for i in range(3):
    z0 = -4.5 + i * 1.32
    box('glass_r%d' % i, (0.02, 2.04, 1.32 - 0.08), (SX1 - 0.075, 0.16 + 1.08, z0 + 0.66), M_glass)
# mullions
for x in (-5.42, -4.10, -2.78, -1.46):
    box('mull_%s' % x, (0.07, 2.16, 0.13), (x, 0.16 + 1.08, SZ1 - 0.07), M_alu)
for z in (-4.50, -3.18, -1.86, -0.54):
    box('mull_r%s' % z, (0.13, 2.16, 0.07), (SX1 - 0.07, 0.16 + 1.08, z), M_alu)
box('rail_f_top', (4.2, 0.10, 0.15), (-3.35, 0.16 + 2.16, SZ1 - 0.07), M_alu)
box('rail_f_bot', (4.2, 0.09, 0.15), (-3.35, 0.16 + 0.02, SZ1 - 0.07), M_alu)

# sliding doors (slightly open for life)
box('door_frame_l', (0.10, 2.20, 0.16), (-1.28, 0.16 + 1.10, SZ1 - 0.08), M_alu)
box('door_frame_r', (0.10, 2.20, 0.16), (-0.32, 0.16 + 1.10, SZ1 - 0.08), M_alu)
box('door_frame_t', (1.06, 0.12, 0.18), (-0.80, 0.16 + 2.22, SZ1 - 0.08), M_alu)
for i in range(2):
    px = -0.80 - 0.245 + i * 0.49 + (-0.10 if i == 0 else 0.10)
    box('door_glass_%d' % i, (0.42, 2.02, 0.02), (px, 0.16 + 1.08, SZ1 - 0.09), M_glass)
    box('door_bar_%d' % i, (0.49, 0.09, 0.05), (px, 0.16 + 2.10, SZ1 - 0.09), M_alu)
    box('door_bar2_%d' % i, (0.49, 0.09, 0.05), (px, 0.16 + 0.06, SZ1 - 0.09), M_alu)

# fascia + sign
box('fascia_f', (5.9, 0.86, 0.34), (cx + 0.06, 2.94, SZ1 + 0.17), M_wall2)
box('fascia_r', (0.34, 0.86, 6.95), (SX1 + 0.17, 2.94, cz - 0.05), M_wall2)
box('fascia_corner', (0.4, 0.86, 0.4), (SX1 + 0.2, 2.94, SZ1 + 0.2), M_wall2)
box('stripe_mint_f', (5.9, 0.09, 0.36), (cx + 0.06, 2.58, SZ1 + 0.18), M_mint)
box('stripe_coral_f', (5.9, 0.07, 0.36), (cx + 0.06, 2.49, SZ1 + 0.18), M_coral)
box('stripe_mint_r', (0.36, 0.09, 6.95), (SX1 + 0.18, 2.58, cz - 0.05), M_mint)
box('stripe_coral_r', (0.36, 0.07, 6.95), (SX1 + 0.18, 2.49, cz - 0.05), M_coral)
box('sign_frame', (4.0, 0.82, 0.04), (-3.0, 2.94, SZ1 + 0.335), M_dark)
box('sign_panel', (3.9, 0.72, 0.06), (-3.0, 2.94, SZ1 + 0.36), M_signface)
# sign text (facing +Z): text lies in XY plane by default, rotate to stand up
text_obj('sign_text', 'ほしぞらマート', 0.34, (-3.05, 3.02, SZ1 + 0.40), M_dark,
         rot=(0, 0, 0))
text_obj('sign_sub', '24H OPEN ・ 年中無休', 0.095, (-3.05, 2.66, SZ1 + 0.40), M_coral,
         rot=(0, 0, 0))
# side sign
text_obj('side_text', '24時間 営業中', 0.26, (SX1 + 0.375, 2.96, -2.60), M_dark,
         rot=(0, math.pi / 2, 0))
box('side_panel', (0.06, 0.66, 3.2), (SX1 + 0.345, 2.94, -2.60), M_signface)
box('side_frame', (0.04, 0.74, 3.3), (SX1 + 0.320, 2.94, -2.60), M_dark)

# canopy over entrance
box('canopy', (3.3, 0.09, 1.05), (-1.15, 2.44, SZ1 + 0.47), M_wall)
box('canopy_edge', (3.34, 0.06, 0.10), (-1.15, 2.39, SZ1 + 0.96), M_wall2)
for i in range(3):
    lx = -2.2 + i * 1.05
    cyl('downlight_%d' % i, 0.055, 0.02, (lx, 2.385, SZ1 + 0.55), M_ceillamp, 12)

# ----------------------------------------------------------------------------- interior
IX0, IX1, IZ0, IZ1 = SX0 + 0.16, SX1 - 0.16, SZ0 + 0.16, SZ1 - 0.16
box('int_floor', (IX1 - IX0, 0.06, IZ1 - IZ0), ((IX0 + IX1) / 2, 0.16, (IZ0 + IZ1) / 2), M_floor)
box('int_ceiling', (IX1 - IX0, 0.06, IZ1 - IZ0), ((IX0 + IX1) / 2, 2.86, (IZ0 + IZ1) / 2), M_wall)
# ceiling light panels
for i in range(2):
    for j in range(3):
        box('ceil_lamp_%d%d' % (i, j), (1.5, 0.05, 0.62), (-4.4 + i * 2.3, 2.815, -4.4 + j * 2.4), M_ceillamp)
# interior lights
for lx, lz in ((-4.2, -3.6), (-2.2, -1.1), (-1.0, -3.4), (-3.4, -0.4)):
    area_light('in_light', (lx, 2.45, lz), 0.5, 1400.0, (1.0, 0.74, 0.46), rot=(0, 0, 0))

# fridge wall (back)
box('fridge_body', (2.05, 2.0, 0.5), (-4.28, 0.16 + 1.0, IZ0 + 0.26), M_wall)
box('fridge_glow', (1.95, 1.85, 0.04), (-4.28, 0.16 + 1.02, IZ0 + 0.06), M_fridge)
for r in range(4):
    y = 0.16 + 0.30 + r * 0.42
    box('fridge_shelf_%d' % r, (1.94, 0.03, 0.36), (-4.28, y, IZ0 + 0.28), M_alu)
    for c in range(9):
        for k in range(2):
            bx = -4.28 - 0.95 + 0.17 + c * 0.215
            bz = IZ0 + 0.24 + k * 0.15
            hh = 0.16 + ((c + r) % 3) * 0.02
            m = PROD_MATS[(c * 3 + r * 5 + k) % len(PROD_MATS)]
            cyl('bottle_%d_%d_%d' % (r, c, k), 0.035, hh, (bx, y + 0.02 + hh / 2, bz), m, 10)
# fridge door frames
for i in range(4):
    box('fridge_mull_%d' % i, (0.05, 2.0, 0.06), (-4.28 - 1.025 + i * (2.05 / 3), 1.16, IZ0 + 0.52), M_alu)

# gondola shelves
def gondola(gx, gz, length, depth, tiers, height):
    box('gond_base_%s' % gx, (length, 0.16, depth), (gx, 0.16 + 0.08, gz), M_alu)
    box('gond_back_%s' % gx, (length, height, 0.05), (gx, 0.16 + height / 2, gz), M_shelf)
    for s in (-1, 1):
        box('gond_cap_%s_%d' % (gx, s), (0.05, height, depth), (gx + s * (length / 2 - 0.025), 0.16 + height / 2, gz), M_shelf)
    for t in range(tiers):
        y = 0.16 + 0.18 + t * ((height - 0.25) / tiers)
        for s in (-1, 1):
            box('gond_board_%s_%d_%d' % (gx, t, s), (length - 0.1, 0.045, depth / 2 - 0.03),
                (gx, y, gz + s * (depth / 4)), M_shelf)
            n = int((length - 0.2) / 0.115)
            for i in range(n):
                px = gx - length / 2 + 0.12 + i * 0.115
                hh = 0.12 + ((i * 37) % 5) * 0.022
                m = PROD_MATS[(t * 13 + i * 5 + (3 if s > 0 else 0)) % len(PROD_MATS)]
                box('prod_%s_%d_%d_%d' % (gx, t, s, i), (0.095, hh, 0.075),
                    (px, y + hh / 2 + 0.022, gz + s * (depth / 4)), m)

gondola(-3.55, -2.55, 2.35, 0.62, 4, 1.42)
gondola(-3.55, -3.85, 2.35, 0.62, 4, 1.42)

# wall shelving (left)
for t in range(4):
    y = 0.16 + 0.35 + t * 0.42
    box('wall_shelf_%d' % t, (0.34, 0.04, 2.6), (IX0 + 0.2, y, -3.2), M_shelf)
    for i in range(18):
        m = PROD_MATS[(i * 3 + t * 7) % len(PROD_MATS)]
        box('wall_prod_%d_%d' % (t, i), (0.2, 0.14, 0.12), (IX0 + 0.22, y + 0.09, -4.45 + i * 0.145), m)

# magazine rack
box('magazine_rack', (2.05, 0.72, 0.34), (-4.0, 0.16 + 0.36, IZ1 - 0.42), mat('rackbody', (0.30, 0.30, 0.30), rough=0.55))
for row in range(3):
    for i in range(14):
        m = PROD_MATS[(i + row * 3) % len(PROD_MATS)]
        box('mag_%d_%d' % (row, i), (0.12, 0.17, 0.012),
            (-4.95 + i * 0.14, 0.16 + 0.22 + row * 0.24 + 0.02, IZ1 - 0.22),
            m, rot=(-0.32, 0, 0))

# counter
box('counter', (1.55, 0.92, 0.45), (-1.55, 0.16 + 0.46, -1.15), M_wall2)
box('counter_top', (1.65, 0.06, 0.57), (-1.55, 0.16 + 0.95, -1.15), M_shelf)
box('counter_stripe', (1.45, 0.05, 0.02), (-1.55, 0.16 + 0.62, -0.92), M_mint)
box('reg', (0.34, 0.12, 0.28), (-1.85, 0.16 + 1.04, -1.15), M_dark)
box('reg_screen', (0.26, 0.19, 0.02), (-1.85, 0.16 + 1.20, -1.09), M_neon_cyan, rot=(-0.22, 0, 0))
box('coffee', (0.30, 0.52, 0.30), (-1.43, 0.16 + 1.26, -1.17), M_dark)
box('coffee_face', (0.22, 0.26, 0.02), (-1.43, 0.16 + 1.38, -1.02), M_warm_lamp)
cyl('oden_pot', 0.26, 0.20, (-1.00, 0.16 + 1.10, -1.15), M_alu, 24, r2=0.24)
cyl('oden_soup', 0.235, 0.02, (-1.00, 0.16 + 1.20, -1.15), mat('soup', (0.55, 0.35, 0.10), rough=0.3), 24)
for i in range(7):
    a = i * 0.9
    sphere('oden_%d' % i, 0.045, (-1.00 + math.cos(a) * 0.13, 0.16 + 1.22, -1.15 + math.sin(a) * 0.13),
           mat('odenball%d' % (i % 4), [(0.85, 0.80, 0.62), (0.75, 0.58, 0.38), (0.62, 0.45, 0.25), (0.90, 0.86, 0.70)][i % 4], rough=0.6), 10)
# back counter shelves
box('back_counter', (1.5, 0.95, 0.4), (-1.55, 0.16 + 0.475, -1.95), M_wall2)
box('back_panel', (1.6, 1.3, 0.06), (-1.55, 0.16 + 1.55, -2.32), M_shelf)
for t in range(3):
    box('back_shelf_%d' % t, (1.55, 0.03, 0.16), (-1.55, 0.16 + 1.15 + t * 0.32, -2.2), M_shelf)
    for i in range(12):
        m = PROD_MATS[(i + t * 3) % len(PROD_MATS)]
        box('cig_%d_%d' % (t, i), (0.055, 0.13, 0.05), (-2.27 + i * 0.13, 0.16 + 1.23 + t * 0.32, -2.2), m)

# hanging lightbox signs inside
box('hangbox1', (0.04, 0.34, 1.2), (-3.9, 2.30, -1.55), M_signface)
box('hangbox2', (0.04, 0.34, 1.35), (-3.9, 2.30, -4.55), M_signface)
text_obj('hang_text1', 'おにぎり・お弁当', 0.15, (-3.875, 2.30, -1.55), M_dark, rot=(0, math.pi / 2, 0))
text_obj('hang_text2', '飲料・お酒', 0.15, (-3.875, 2.30, -4.55), M_dark, rot=(0, math.pi / 2, 0))

# ----------------------------------------------------------------------------- props
# entrance mat
box('mat', (1.16, 0.02, 0.72), (-0.79, 0.161, 0.98), mat('mat', (0.10, 0.13, 0.20), rough=0.85))
# umbrella stand
cyl('ustand', 0.19, 0.42, (-2.0, 0.15 + 0.21, 1.32), M_alu, 16)
for i in range(3):
    a = i * 2.1 + 0.4
    ox, oz = math.cos(a) * 0.07, math.sin(a) * 0.07
    m = PROD_MATS[(i * 4) % len(PROD_MATS)]
    ob = cyl('umb_%d' % i, 0.085, 0.62, (-2.0 + ox, 0.15 + 0.52, 1.32 + oz), m, 10, r2=0.045)
    ob.rotation_euler = Euler((math.sin(a) * 0.2, 0, math.cos(a) * 0.2))
    tube('umb_shaft_%d' % i, (-2.0 + ox, 0.15 + 0.2, 1.32 + oz), (-2.0 + ox * 1.3, 0.15 + 1.0, 1.32 + oz * 1.3), 0.012, M_alu)
# A-frame board
box('aframe_l', (0.46, 0.62, 0.02), (-2.55, 0.15 + 0.36, 1.25), M_dark, rot=(0, 0.16, 0))
box('aframe_r', (0.46, 0.62, 0.02), (-2.43, 0.15 + 0.36, 1.25), M_dark, rot=(0, -0.16, 0))
text_obj('aframe_t', 'おでん', 0.10, (-2.49, 0.15 + 0.52, 1.27), M_warm_lamp, rot=(0, 0, 0))

# vending machine
VX, VZ = 0.62, 1.28
box('vend', (1.0, 1.86, 0.72), (VX, 0.15 + 0.93, VZ), mat('vendbody', (0.72, 0.75, 0.80), rough=0.4))
box('vend_band', (1.02, 0.16, 0.74), (VX, 0.15 + 1.56, VZ), mat('vendband', (0.05, 0.38, 0.50), rough=0.4))
box('vend_face', (0.88, 1.04, 0.02), (VX, 0.15 + 1.16, VZ + 0.365), mat('vendface', (1, 1, 1), rough=0.3, emit=(0.85, 0.94, 1.0), emit_str=3.0))
for r in range(5):
    for c in range(4):
        m = PROD_MATS[(r * 4 + c) % len(PROD_MATS)]
        box('venddrink_%d_%d' % (r, c), (0.14, 0.15, 0.02),
            (VX - 0.33 + c * 0.22, 0.15 + 1.55 - r * 0.19, VZ + 0.378), m)
box('vend_slot', (0.76, 0.2, 0.04), (VX, 0.15 + 0.20, VZ + 0.37), M_dark)
box('vend_sign', (0.88, 0.24, 0.02), (VX, 0.15 + 1.72, VZ + 0.372), mat('vendsign', (1, 1, 1), emit=(0.9, 0.97, 1.0), emit_str=5.0))
text_obj('vend_text', 'つめた〜い', 0.12, (VX, 0.15 + 1.72, VZ + 0.385), mat('vendtext', (0.05, 0.35, 0.45)), rot=(0, 0, 0))

# trash bins
for i, c in enumerate([(0.85, 0.60, 0.15), (0.10, 0.32, 0.60), (0.10, 0.55, 0.35)]):
    cyl('bin_%d' % i, 0.13, 0.52, (1.28, 0.15 + 0.26, 0.92 + (i - 1) * 0.30), M_pole, 14)
    cyl('bin_lid_%d' % i, 0.135, 0.05, (1.28, 0.15 + 0.54, 0.92 + (i - 1) * 0.30), mat('binlid%d' % i, c, rough=0.5), 14)

# bicycle (simplified)
def wheel(x, z, r=0.32):
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=False, segments=24, radius=r)
    me = bpy.data.meshes.new('wheel')
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new('wheel', me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(M_dark)
    cu = ob.modifiers.new('bevel', 'BEVEL')
    cu.width = 0.03
    cu.segments = 2
    ob.location = (x, 0.15 + r, z)
    ob.rotation_euler = Euler((0, 0, 0))
    ob.rotation_euler.rotate_axis('X', math.pi / 2)
    return ob

BX, BZ = -4.55, 1.28
wheel(BX - 0.52, BZ)
wheel(BX + 0.52, BZ)
bike_mat = mat('bike', (0.62, 0.10, 0.12), rough=0.35, metal=0.4)
for a, b in [((BX - 0.52, 0.47, BZ), (BX - 0.06, 0.77, BZ)),
             ((BX - 0.06, 0.77, BZ), (BX + 0.42, 0.81, BZ)),
             ((BX - 0.06, 0.45, BZ), (BX + 0.42, 0.81, BZ)),
             ((BX - 0.52, 0.47, BZ), (BX - 0.06, 0.45, BZ)),
             ((BX + 0.42, 0.81, BZ), (BX + 0.52, 0.47, BZ))]:
    tube('biketube', a, b, 0.022, bike_mat)
box('bike_seat', (0.2, 0.05, 0.1), (BX - 0.09, 0.83, BZ), M_dark)
tube('bike_bar', (BX + 0.40, 0.86, BZ - 0.2), (BX + 0.40, 0.86, BZ + 0.2), 0.016, M_dark)
box('bike_basket', (0.28, 0.22, 0.24), (BX + 0.62, 0.71, BZ), M_alu)

# notice board on right wall
box('notice', (0.04, 0.95, 1.15), (SX1 + 0.10, 1.62, -5.55), mat('wood', (0.32, 0.22, 0.12), rough=0.7))
for i in range(3):
    box('notice_p%d' % i, (0.012, 0.42, 0.26), (SX1 + 0.13, 1.62 + (0.16 if i % 2 else -0.06), -5.85 + i * 0.3),
        mat('notepaper%d' % i, [(0.85, 0.82, 0.72), (0.90, 0.86, 0.74), (0.80, 0.86, 0.80)][i], rough=0.8))

# AC units
def ac_unit(loc, rotz=0.0, s=1.0):
    box('ac', (0.52 * s, 0.6 * s, 0.38 * s), loc, mat('acbody', (0.60, 0.62, 0.65), rough=0.5), rot=(0, 0, rotz))
    cyl('ac_fan', 0.2 * s, 0.03, (loc[0], loc[1], loc[2] + 0.2 * s), M_dark, 20, rot=(math.pi / 2, 0, 0))
ac_unit((0.12, 0.55, -5.55), -math.pi / 2)
ac_unit((-4.2, 3.62, -2.0), 0, 1.15)
ac_unit((-1.4, 3.62, -4.6), 0, 0.9)

# rooftop clutter
for i in range(3):
    cyl('vent_%d' % i, 0.07, 0.6, (-4.6 + i * 0.7, 3.65, 0.2), M_alu, 12)
cyl('watertank', 0.42, 0.55, (-1.2, 3.65, -1.4), mat('tank', (0.55, 0.57, 0.60), rough=0.5), 20)

# ----------------------------------------------------------------------------- street furniture
# street lamp (right side, arm over the road)
LX, LZ = 4.28, 1.42
cyl('lamp_pole', 0.075, 4.3, (LX, 0.15 + 2.15, LZ), M_pole, 14)
cyl('lamp_base', 0.16, 0.24, (LX, 0.15 + 0.12, LZ), M_dark, 14)
poly_curve('lamp_arm', [(LX, 4.35, LZ), (LX - 0.5, 4.62, LZ - 0.3), (LX - 1.05, 4.52, LZ - 0.75), (LX - 1.18, 4.42, LZ - 0.85)], 0.05, M_pole)
box('lamp_head', (0.5, 0.12, 0.26), (LX - 1.22, 4.4, LZ - 0.88), M_dark, rot=(0, 0.1, 0))
box('lamp_bulb', (0.4, 0.04, 0.18), (LX - 1.22, 4.33, LZ - 0.88), M_warm_lamp)
spot_light('lamp_spot', (LX - 1.22, 4.3, LZ - 0.88), (LX - 1.4, 0, LZ - 2.6), 3500.0, (1.0, 0.78, 0.50), angle=1.1, blend=0.6, radius=0.2)

# utility poles + wires
def utility_pole(x, z, h):
    cyl('upole', 0.085, h, (x, h / 2 + 0.15, z), M_pole, 12)
    for i, y in enumerate((h * 0.72 + 0.15, h * 0.84 + 0.15, h * 0.93 + 0.15)):
        box('uarm_%d_%.2f' % (i, x), (1.5 - i * 0.25, 0.06, 0.07), (x, y, z), M_dark)
        for k in (-1, 1):
            cyl('uins', 0.035, 0.1, (x + k * (0.55 - i * 0.1), y + 0.08, z), M_wall, 8)
    cyl('utrans', 0.17, 0.52, (x + 0.26, h * 0.60 + 0.20, z), M_alu, 14)
    for i in range(4):
        cyl('ustripe_%d_%.2f' % (i, x), 0.118, 0.12, (x, 0.35 + i * 0.12, z),
            mat('stripe%d' % (i % 2), (0.85, 0.70, 0.12) if i % 2 else (0.05, 0.05, 0.06), rough=0.6), 12)

utility_pole(-6.02, 1.52, 5.2)
utility_pole(4.45, -1.45, 5.5)

def wire(a, b, sag, r=0.008):
    pts = []
    n = 12
    for i in range(n + 1):
        t = i / n
        p = Vector(a).lerp(Vector(b), t)
        p.y -= sag * 4 * t * (1 - t)
        pts.append(p)
    poly_curve('wire', pts, r, M_dark)

A = (-6.02, 0, 1.52)
B = (4.45, 0, -1.45)
for i in range(3):
    for k in (-1, 1):
        wire((A[0] + k * (0.55 - i * 0.1), 5.2 * (0.72 + i * 0.11) + 0.27, A[2]),
             (B[0] + k * (0.55 - i * 0.1), 5.5 * (0.72 + i * 0.11) + 0.27, B[2]), 0.6 + i * 0.2)

# street sign
cyl('sgn_pole', 0.045, 2.9, (1.30, 0.15 + 1.45, 1.90), M_alu, 10)
box('sgn_plate', (0.9, 0.22, 0.03), (1.30, 2.62, 1.90), mat('signplate', (0.06, 0.20, 0.36), rough=0.4), rot=(0, 0.5, 0))
text_obj('sgn_text', 'ほしぞら通り', 0.085, (1.30 + math.sin(0.5) * 0.03, 2.62, 1.90 + math.cos(0.5) * 0.03), M_paint, rot=(0, 0.5, 0))

# traffic light (green, on the right pole)
box('tl_arm', (1.9, 0.09, 0.09), (3.50, 4.38, -1.45), M_dark)
box('tl_head', (0.6, 0.24, 0.2), (2.60, 4.38, -1.45), M_dark)
for dx, m in ((-0.18, M_red_light), (0.0, mat('amber', (0.5, 0.32, 0.05), emit=(0.6, 0.35, 0.05), emit_str=0.4)), (0.18, M_green)):
    cyl('tl_lens', 0.07, 0.03, (2.60 + dx, 4.38, -1.34), m, 14, rot=(math.pi / 2, 0, 0))

# guardrails on the far sidewalk
def guardrail(x, z, length, rotz=0.0):
    for i in range(int(length / 1.3) + 1):
        px = x - length / 2 + i * (length / max(1, int(length / 1.3)))
        cyl('gr_post', 0.035, 0.8, (px, 0.15 + 0.4, z), M_wall, 8)
    box('gr_beam', (length, 0.11, 0.05), (x, 0.15 + 0.72, z), M_wall, rot=(0, 0, rotz))
    box('gr_beam2', (length, 0.06, 0.04), (x, 0.15 + 0.46, z), M_wall, rot=(0, 0, rotz))

guardrail(-4.9, 4.30, 3.0)
guardrail(-1.9, 4.30, 2.6)
guardrail(2.85, 5.05, 1.9)

# ----------------------------------------------------------------------------- alley wall
box('alley_wall', (0.18, 4.3, 8.4), (-6.42, 2.15, -2.3), mat('concrete', (0.28, 0.28, 0.30), rough=0.75))
for i in range(3):
    cyl('pipe_%d' % i, 0.045, 4.2, (-6.30, 2.15, -0.4 - i * 2.4), M_alu, 10)
box('alley_lamp', (0.09, 0.03, 0.09), (-6.03, 2.88, -1.9), M_warm_lamp)
point_light('alley_pt', (-6.0, 2.85, -1.9), 220.0, (1.0, 0.75, 0.45), 0.15)

# ----------------------------------------------------------------------------- background city
def building(x, z, w, h, d, cols, rows, lit=0.35, seed=0):
    rnd = random.Random(seed)
    body_m = mat('bmat%d' % seed, (0.10 + rnd.random() * 0.05, 0.11 + rnd.random() * 0.05, 0.13 + rnd.random() * 0.06), rough=0.75)
    box('bld', (w, h, d), (x, h / 2, z), body_m)
    for c in range(cols):
        for r in range(rows):
            wx = x - w / 2 + w * (c + 0.5) / cols
            wy = h * (r + 0.55) / (rows + 0.4)
            if rnd.random() < lit:
                warm = rnd.random() < 0.65
                m = mat('win%d_%d_%d' % (seed, c, r),
                        (1.0, 0.72, 0.35) if warm else (0.45, 0.65, 0.95), rough=0.6,
                        emit=(1.0, 0.70, 0.32) if warm else (0.40, 0.62, 0.95),
                        emit_str=2.2 if warm else 1.6)
                box('win', (w / cols * 0.5, h / rows * 0.45, 0.06), (wx, wy, z + d / 2 + 0.02), m)

building(-5.05, -6.28, 2.9, 6.4, 0.44, 4, 7, 0.34, 1)
building(-2.15, -6.28, 2.8, 4.9, 0.44, 4, 5, 0.42, 2)
building(0.50, -6.28, 2.5, 6.9, 0.44, 3, 7, 0.30, 3)
building(3.10, -6.28, 2.6, 4.2, 0.44, 3, 4, 0.46, 4)
building(5.60, -6.28, 2.4, 5.6, 0.44, 3, 6, 0.36, 5)

# neon sign on the back building
box('neon', (0.1, 1.5, 0.42), (-0.55, 4.55, -6.02), M_neon_pink)
text_obj('neon_text', 'スナック', 0.30, (-0.55, 4.55, -5.96), mat('neontext', (1, 1, 1), emit=(1.0, 0.55, 0.75), emit_str=6.0),
         rot=(0, 0, 0))
point_light('neon_pt', (-0.55, 4.4, -5.4), 420.0, (1.0, 0.35, 0.65), 0.3)

# warm lantern across the right road
sphere('lantern', 0.16, (5.25, 2.2, -4.35), mat('lanternm', (1.0, 0.45, 0.2), emit=(1.0, 0.42, 0.16), emit_str=6.0), 12)
point_light('lantern_pt', (5.1, 2.0, -4.2), 260.0, (1.0, 0.45, 0.2), 0.2)

# ----------------------------------------------------------------------------- atmosphere
# moonlight (big area light above)
area_light('moon', (-8, 15, 9), 9.0, 1500.0, (0.50, 0.63, 1.0), rot=(0, 0, 0))
# cool fill from the sky side
area_light('fill', (9, 9, 13), 12.0, 260.0, (0.45, 0.58, 0.90))
# warm bounce from the shop for the sidewalk
point_light('door_warm', (-1.0, 2.3, 1.4), 260.0, (1.0, 0.66, 0.34), 0.4)

# ----------------------------------------------------------------------------- rain
rain_root = bpy.data.meshes.new('rain_src')
_ = rain_root
rain_mesh = None
RAIN_N = 0 if '--norain' in argv else 700
for i in range(RAIN_N):
    x = random.uniform(-8, 8)
    z = random.uniform(-8, 8)
    y = random.uniform(0.2, 9.5)
    h = random.uniform(0.30, 0.62)
    ob = box('rain%d' % i, (0.006, h, 0.006), (x, y, z), M_rain)
    ob.rotation_euler = Euler((0.03, 0, 0))
    ob.visible_shadow = False

# ----------------------------------------------------------------------------- camera
cam_data = bpy.data.cameras.new('cam')
cam = bpy.data.objects.new('cam', cam_data)
bpy.context.collection.objects.link(cam)
scene.camera = cam
cam_data.lens = 50
cam_data.sensor_width = 36
cam_data.dof.use_dof = True
cam_data.dof.aperture_fstop = 1.8
# position/orientation are set after the Y-up -> Z-up conversion below

# ----------------------------------------------------------------------------- Y-up -> Z-up
# The whole scene is authored in Y-up (three.js convention); Blender is Z-up.
root = bpy.data.objects.new('scene_root', None)
bpy.context.collection.objects.link(root)
for ob in list(bpy.context.scene.objects):
    if ob is not root and ob.parent is None and ob.type in {'MESH', 'CURVE', 'FONT', 'LIGHT'}:
        ob.parent = root
root.rotation_euler = (math.pi / 2, 0, 0)
bpy.context.view_layer.update()

# camera in Blender's native Z-up frame  (Y-up (x,y,z)  ->  (x, -z, y))
CAM_POS = Vector((11.8, -14.7, 9.3))
CAM_TGT = Vector((-1.5, 0.9, 1.6))
cam.location = CAM_POS
cam_dir = CAM_TGT - CAM_POS
cam.rotation_euler = cam_dir.to_track_quat('-Z', 'Y').to_euler()
cam.data.dof.focus_distance = cam_dir.length * 0.86
bpy.context.view_layer.update()

# ----------------------------------------------------------------------------- render
scene.render.threads_mode = 'AUTO'

if '--animate' in argv:
    import os as _os
    ANIM_FRAMES = int(arg('--frames', 36))
    FSTART = int(arg('--fstart', 0))
    FEND = int(arg('--fend', ANIM_FRAMES))
    FPS = int(arg('--fps', 12))
    OUTPAT = arg('--outpat', 'frames/f_')
    _os.makedirs(_os.path.dirname(OUTPAT) or '.', exist_ok=True)

    door_prev = {}
    rain_objs = [o for o in bpy.data.objects if o.name.startswith('rain')]
    door_l = bpy.data.objects.get('door_glass_0')
    door_r = bpy.data.objects.get('door_glass_1')
    door_lb = bpy.data.objects.get('door_bar_0')
    door_rb = bpy.data.objects.get('door_bar_1')
    door_l2 = bpy.data.objects.get('door_bar2_0')
    door_r2 = bpy.data.objects.get('door_bar2_1')
    sign_bsdf = None
    for n in M_signface.node_tree.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            sign_bsdf = n
    tl_green = bpy.data.objects.get('tl_lens')
    # camera orbit parameters (Z-up world)
    base_az = math.atan2(CAM_POS.y - CAM_TGT.y, CAM_POS.x - CAM_TGT.x)
    base_dist = (CAM_POS - CAM_TGT).length
    base_el = math.asin((CAM_POS.z - CAM_TGT.z) / base_dist)

    scene.render.fps = FPS
    for f in range(FSTART, FEND):
        t = f / FPS
        # --- rain fall + wrap
        for i, ro in enumerate(rain_objs):
            ro.location.z -= (5.5 + (i % 7) * 0.35) / FPS
            if ro.location.z < 0.05:
                ro.location.z += 9.5
        # --- automatic door: open 4.0-7.0s of a 11s cycle
        cyc = t % 11.0
        k = 0.0
        if 3.2 < cyc < 7.4:
            a = cyc - 3.2
            b = 7.4 - cyc
            k = min(1.0, a / 0.85, b / 0.85)
            k = k * k * (3 - 2 * k)
        for ob, sgn in ((door_l, -1), (door_r, 1), (door_lb, -1), (door_rb, 1), (door_l2, -1), (door_r2, 1)):
            if ob is not None:
                prev = door_prev.get(ob.name, 0.0)
                ob.location.x += sgn * 0.44 * (k - prev)
                door_prev[ob.name] = k
        # --- sign flicker
        flick = 0.45 + 0.035 * math.sin(t * 13.7) * math.sin(t * 4.3)
        if math.sin(t * 0.37) > 0.994:
            flick *= 0.7
        if sign_bsdf is not None:
            for nm in ('Emission Strength',):
                if nm in sign_bsdf.inputs:
                    sign_bsdf.inputs[nm].default_value = flick
        # --- traffic light blink
        if tl_green is not None:
            tl_green.data.materials[0] = M_red_light if (t % 16) > 9.5 else M_green
        # --- slow camera orbit
        az = base_az + 0.10 * math.sin(t * 0.35)
        r = base_dist * (1.0 - 0.03 * math.sin(t * 0.3))
        cam.location = (CAM_TGT.x + r * math.cos(base_el) * math.cos(az),
                        CAM_TGT.y + r * math.cos(base_el) * math.sin(az),
                        CAM_TGT.z + r * math.sin(base_el))
        cam.rotation_euler = (CAM_TGT - cam.location).to_track_quat('-Z', 'Y').to_euler()

        scene.render.filepath = OUTPAT + str(f).zfill(4) + '.png'
        bpy.ops.render.render(write_still=True)
        print('FRAME', f, 'done')
    print('ANIM_DONE', FSTART, FEND)
else:
    bpy.ops.render.render(write_still=True)
    print('RENDER_DONE', OUT)
