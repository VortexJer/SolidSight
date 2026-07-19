# make_blind.py -- procedural BVH parkour clip (stdlib + numpy only)
# 240 frames @ 30 fps: run approach, vault a 0.9 m obstacle, land+absorb,
# 90-degree left turn, two strides to a stop.
import os, math
import numpy as np

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_BVH = os.path.join(OUT_DIR, "parkour_blind.bvh")

FPS = 30
N = 240
DT = 1.0 / FPS
M = 100.0                       # meters -> centimeters

L1, L2 = 0.42, 0.40             # thigh, shin (m)
HIPJ_L = np.array([0.09, -0.04, 0.0])
HIPJ_R = np.array([-0.09, -0.04, 0.0])
TOE_REL = np.array([0.0, -0.06, 0.13])    # toe joint rel ankle, foot frame
HEEL_REL = np.array([0.0, -0.07, -0.05])  # heel point rel ankle
ANKLE_H = 0.08                  # ankle height, flat foot

def rx(a):
    a = math.radians(a); c, s = math.cos(a), math.sin(a)
    return np.array([[1.0,0,0],[0,c,-s],[0,s,c]])
def ry(a):
    a = math.radians(a); c, s = math.cos(a), math.sin(a)
    return np.array([[c,0,s],[0,1.0,0],[-s,0,c]])
def rz(a):
    a = math.radians(a); c, s = math.cos(a), math.sin(a)
    return np.array([[c,-s,0],[s,c,0],[0,0,1.0]])

def zxy_from_matrix(R):
    """Decompose R = Rz(z)@Rx(x)@Ry(y), picking the branch with small y,z."""
    sx = max(-1.0, min(1.0, R[2,1]))
    m = math.hypot(R[2,0], R[2,2])
    cands = []
    if m > 1e-9:
        x1 = math.degrees(math.atan2(sx, m))
        y1 = math.degrees(math.atan2(-R[2,0], R[2,2]))
        z1 = math.degrees(math.atan2(-R[0,1], R[1,1]))
        cands.append((z1, x1, y1))
        x2 = math.degrees(math.atan2(sx, -m))
        y2 = math.degrees(math.atan2(R[2,0], -R[2,2]))
        z2 = math.degrees(math.atan2(R[0,1], -R[1,1]))
        cands.append((z2, x2, y2))
    else:
        x1 = 90.0 if sx > 0 else -90.0
        z1 = math.degrees(math.atan2(R[1,0], R[0,0]))
        cands.append((z1, x1, 0.0))
    best = min(cands, key=lambda c: abs(c[0]) + abs(c[2]))
    z, x, y = best
    Rc = rz(z) @ rx(x) @ ry(y)
    assert np.abs(Rc - R).max() < 1e-5, "euler decomposition failed"
    return z, x, y

def smoothstep(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)

class Curve:
    """Monotone cubic (PCHIP / Fritsch-Carlson) interpolation of keyframes."""
    def __init__(self, pairs):
        ts = np.array([p[0] for p in pairs], float)
        vs = np.array([p[1] for p in pairs], float)
        assert np.all(np.diff(ts) > 0), "curve keys must be strictly increasing"
        self.ts, self.vs = ts, vs
        h = np.diff(ts); d = np.diff(vs) / h
        n = len(ts); m = np.zeros(n)
        if n == 2:
            m[:] = d[0]
        else:
            m[0] = d[0]; m[-1] = d[-1]
            for i in range(1, n - 1):
                if d[i-1] == 0.0 or d[i] == 0.0 or d[i-1] * d[i] < 0.0:
                    m[i] = 0.0
                else:
                    w1 = 2*h[i] + h[i-1]; w2 = h[i] + 2*h[i-1]
                    m[i] = (w1 + w2) / (w1 / d[i-1] + w2 / d[i])
        self.h, self.m = h, m
    def __call__(self, t):
        ts, vs, h, m = self.ts, self.vs, self.h, self.m
        t = min(max(float(t), ts[0]), ts[-1])
        i = int(np.searchsorted(ts, t, side='right') - 1)
        i = min(max(i, 0), len(h) - 1)
        u = (t - ts[i]) / h[i]
        h00 = 2*u**3 - 3*u**2 + 1; h10 = u**3 - 2*u**2 + u
        h01 = -2*u**3 + 3*u**2;    h11 = u**3 - u**2
        return h00*vs[i] + h10*h[i]*m[i] + h01*vs[i+1] + h11*h[i]*m[i+1]

# ----------------------------------------------------------------------------
# Body trajectory keyframes (frames ; meters / degrees)
# ----------------------------------------------------------------------------
HIP_X = Curve([(0,0.0),(88,0.0),(98,0.02),(108,0.10),(118,0.30),(128,0.58),
               (138,0.92),(150,1.42),(162,2.00),(174,2.38),(188,2.55),
               (205,2.60),(239,2.60)])
HIP_Z = Curve([(0,0.00),(5,0.45),(17,1.50),(29,2.60),(41,3.70),(55,4.78),
               (59,5.00),(68,5.78),(77,6.48),(86,6.72),(98,6.93),(108,7.00),
               (118,7.06),(128,7.14),(138,7.19),(150,7.20),(239,7.20)])
HIP_Y = Curve([(0,0.88),(5,0.855),(11,0.905),(17,0.855),(23,0.905),(29,0.855),
               (35,0.905),(41,0.855),(47,0.905),(51,0.87),(55,0.80),(59,1.00),
               (68,1.43),(77,0.97),(81,0.88),(86,0.76),(93,0.80),(100,0.865),
               (112,0.88),(120,0.87),(130,0.885),(140,0.872),(152,0.885),
               (164,0.878),(176,0.89),(190,0.90),(205,0.905),(239,0.902)])
PATH_YAW = Curve([(0,0),(88,0),(98,8),(108,22),(118,40),(128,62),(138,82),
                  (148,90),(239,90)])
OSC_YAW = Curve([(0,4),(2,6),(14,-6),(26,6),(38,-6),(50,7),(56,4),(66,0),
                 (77,-5),(88,0),(108,-4),(126,4),(136,-3),(156,2),(170,-1),
                 (190,0),(239,0)])
ROLL = Curve([(0,-1),(5,-3),(17,3),(29,-3),(41,3),(54,-2),(66,0),(86,2),
              (110,7),(125,5),(140,3),(155,1),(170,0),(239,0)])
ROOT_PITCH = Curve([(0,8),(26,9),(41,10),(50,13),(55,24),(59,4),(64,14),
                    (68,22),(73,14),(77,17),(86,26),(93,22),(100,14),(112,11),
                    (126,9),(140,8),(156,6),(170,4),(185,2),(205,1),(239,1)])
SPINE_X = Curve([(0,3),(50,6),(55,12),(59,-2),(68,10),(77,6),(86,14),(96,8),
                 (110,5),(140,4),(170,3),(200,2),(239,2)])
CHEST_LEAD = Curve([(0,0),(88,0),(98,8),(112,12),(128,8),(145,0),(239,0)])
LOOK = Curve([(0,0),(78,0),(88,14),(98,26),(112,22),(130,10),(145,0),(239,0)])
SWAY = Curve([(0,-0.015),(5,-0.02),(11,0),(17,0.02),(23,0),(29,-0.02),(35,0),
              (41,0.02),(47,0),(55,-0.02),(66,0),(77,0.02),(88,-0.01),
              (100,0.01),(112,0.03),(130,-0.03),(148,0.03),(163,-0.02),
              (178,0.01),(195,0),(239,0)])
ARM_L = Curve([(0,-20),(2,-30),(14,28),(26,-32),(38,30),(50,-35),(55,42),
               (60,-25),(65,-75),(71,-60),(77,-25),(86,18),(96,8),(108,15),
               (126,-16),(136,12),(156,-10),(170,6),(185,2),(239,2)])
ARM_R = Curve([(0,20),(2,30),(14,-28),(26,32),(38,-30),(50,40),(55,45),
               (60,-25),(65,-75),(71,-60),(77,-25),(86,18),(96,8),(108,-15),
               (126,14),(136,-12),(156,9),(170,-5),(185,2),(239,2)])
ELBOW = Curve([(0,-45),(50,-50),(55,-62),(60,-28),(65,-20),(71,-30),(77,-42),
               (86,-58),(100,-46),(126,-38),(140,-32),(156,-26),(170,-20),
               (190,-14),(239,-12)])
ABD = Curve([(0,5),(55,6),(62,20),(70,28),(77,14),(88,8),(120,6),(160,5),
             (200,4),(239,4)])

# Ballistic flight of the hips over the obstacle (frames 59..77)
T_TAKEOFF, T_LAND = 59, 77
V0_JUMP, G = 2.8883, 9.81 * 0.5  # y = 1.00 + v0*t - 4.905*t^2

RUN_ARC  = [(0,0),(0.4,0.09),(0.8,0.03),(1,0)]
WALK_ARC = [(0,0),(0.4,0.06),(1,0)]

# ----------------------------------------------------------------------------
# Footstep plan.  Each plant: ankle (x,z) when flat, foot yaw, frame span,
# entry pitch (neg = heel-first, pos = toe-first), exit (toe-off) pitch,
# optional custom swing height/pitch profiles for the swing INTO this plant.
# ----------------------------------------------------------------------------
L_PLANTS = [
    dict(x=0.10, z=-0.60, yaw=0,  t0=-20, t1=-3,  entry=-12, exit=45),
    dict(x=0.10, z=1.50,  yaw=0,  t0=14,  t1=21,  entry=-12, exit=45),
    dict(x=0.10, z=3.70,  yaw=0,  t0=38,  t1=45,  entry=-12, exit=50),
    dict(x=0.10, z=6.50,  yaw=0,  t0=77,  t1=98,  entry=25,  exit=30,
         sw_h=[(0,0),(0.2,0.25),(0.45,0.7),(0.62,1.0),(0.75,1.02),(0.9,0.5),(1,0)],
         sw_p=[(0,50),(0.25,20),(0.5,-5),(0.7,10),(0.85,20),(1,25)]),
    dict(x=0.36, z=7.02,  yaw=45, t0=108, t1=124, entry=-10, exit=25, sw_h=WALK_ARC),
    dict(x=1.75, z=7.10,  yaw=90, t0=136, t1=158, entry=-10, exit=25, sw_h=WALK_ARC),
    dict(x=2.75, z=7.10,  yaw=90, t0=170, t1=246, entry=-8,  exit=0,  sw_h=WALK_ARC),
]
R_PLANTS = [
    dict(x=-0.10, z=-0.65, yaw=0,  t0=-32, t1=-15, entry=-12, exit=45),
    dict(x=-0.10, z=0.45,  yaw=0,  t0=2,   t1=9,   entry=-12, exit=45),
    dict(x=-0.10, z=2.60,  yaw=0,  t0=26,  t1=33,  entry=-12, exit=45),
    dict(x=-0.08, z=4.75,  yaw=0,  t0=50,  t1=59,  entry=-12, exit=60),
    dict(x=-0.12, z=6.85,  yaw=0,  t0=83,  t1=116, entry=20,  exit=25,
         sw_h=[(0,0),(0.25,0.5),(0.42,0.95),(0.55,1.05),(0.68,0.9),(0.85,0.35),(1,0)],
         sw_p=[(0,60),(0.3,25),(0.55,0),(0.8,15),(1,20)]),
    dict(x=0.95, z=7.30,  yaw=90, t0=126, t1=142, entry=-10, exit=25, sw_h=WALK_ARC),
    dict(x=2.45, z=7.30,  yaw=90, t0=156, t1=246, entry=-8,  exit=0,  sw_h=WALK_ARC),
]

def stance_pose(pl, s):
    """Ankle position / foot pitch / yaw at stance phase s in [0,1].
    Heel-strike pivots about the heel, toe-off (and toe-first landings)
    pivot about the toe so the contact point never slides."""
    s = max(0.0, min(1.0, s))
    ep, xp = pl['entry'], pl['exit']
    if s < 0.15 and ep != 0:
        th = ep * (1.0 - s / 0.15)
    elif s > 0.62 and xp != 0:
        u = (s - 0.62) / 0.38
        th = xp * u * u
    else:
        th = 0.0
    Ryw = ry(pl['yaw'])
    ankle_flat = np.array([pl['x'], ANKLE_H, pl['z']])
    if th > 1e-9:
        piv = ankle_flat + Ryw @ TOE_REL
        ank = piv - Ryw @ (rx(th) @ TOE_REL)
    elif th < -1e-9:
        piv = ankle_flat + Ryw @ HEEL_REL
        ank = piv - Ryw @ (rx(th) @ HEEL_REL)
    else:
        ank = ankle_flat
    return ank, th, pl['yaw']

def stance_toe(pl, th):
    """Toe joint X while in stance: toes stay flat under pivots."""
    if th > 0:
        return -0.9 * th
    if th < 0 and pl['entry'] < 0:
        return 3.0 * min(1.0, th / pl['entry'])
    if th < 0:
        return 0.0
    return 0.0

def foot_state(plants, f):
    """Return (ankle_world_m, foot_pitch_deg, foot_yaw_deg, toe_x_deg)."""
    for i, pl in enumerate(plants):
        if pl['t0'] <= f <= pl['t1']:
            s = (f - pl['t0']) / max(pl['t1'] - pl['t0'], 1)
            ank, th, yaw = stance_pose(pl, s)
            return ank, th, yaw, stance_toe(pl, th)
    for i in range(len(plants) - 1):
        A, B = plants[i], plants[i + 1]
        if A['t1'] < f < B['t0']:
            u = (f - A['t1']) / float(B['t0'] - A['t1'])
            pa, tha, yawa = stance_pose(A, 1.0)
            pb, thb, yawb = stance_pose(B, 0.0)
            ssu = smoothstep(u)
            pos = pa + (pb - pa) * ssu
            arc = Curve(B.get('sw_h', RUN_ARC))
            pos = pos + np.array([0.0, arc(u), 0.0])
            if 'sw_p' in B:
                pitch = Curve(B['sw_p'])(u)
            else:
                pitch = Curve([(0, tha), (0.3, 12), (0.7, -8), (1, thb)])(u)
            yaw = yawa + (yawb - yawa) * ssu
            toe_a = -0.9 * max(tha, 0.0)
            toe_b = -0.9 * thb if thb > 0 else 3.0
            toe = Curve([(0, toe_a), (0.35, 8), (1, toe_b)])(u)
            return pos, pitch, yaw, toe
    # before first / after last plant (should not happen inside 0..N)
    pl = plants[0] if f < plants[0]['t0'] else plants[-1]
    ank, th, yaw = stance_pose(pl, 0.0 if f < pl['t0'] else 1.0)
    return ank, th, yaw, 0.0

# ----------------------------------------------------------------------------
# Two-bone analytic leg IK
# ----------------------------------------------------------------------------
def frame_from(down_dir, ref):
    """Orthonormal frame whose -Y axis is down_dir, +Z near ref."""
    y = -down_dir
    z = ref - y * float(ref @ y)
    zn = np.linalg.norm(z)
    if zn < 1e-6:
        ref2 = np.array([0.0, 1.0, 0.0])
        z = ref2 - y * float(ref2 @ y)
        zn = np.linalg.norm(z)
    z = z / zn
    x = np.cross(y, z)
    return np.column_stack([x, y, z])

def solve_leg(hipw, ankw, Rroot, pole_w):
    """Return (R_upleg_local, R_knee_local, R_shin_in_root)."""
    d = Rroot.T @ (ankw - hipw)
    pol = Rroot.T @ pole_w
    Lr = np.linalg.norm(d)
    n = d / max(Lr, 1e-9)
    Lc = min(max(Lr, 0.20), (L1 + L2) * 0.995)
    ca = (L1 * L1 + Lc * Lc - L2 * L2) / (2.0 * L1 * Lc)
    ca = min(max(ca, -1.0), 1.0)
    sa = math.sqrt(1.0 - ca * ca)
    mv = pol - n * float(n @ pol)
    nm = np.linalg.norm(mv)
    if nm < 1e-6:
        mv = np.array([0.0, 0.0, 1.0]) - n * n[2]
        nm = np.linalg.norm(mv)
    mv = mv / nm
    thigh = ca * n + sa * mv
    knee = L1 * thigh
    shin = n * Lc - knee
    shin = shin / np.linalg.norm(shin)
    A_th = frame_from(thigh, pol)
    A_sh = frame_from(shin, pol)
    return A_th, A_th.T @ A_sh, A_sh

# ----------------------------------------------------------------------------
# Skeleton (offsets in cm).  21 joints, End Sites on head, hands, toes.
# ----------------------------------------------------------------------------
SKEL = ("Hips", (0, 0, 0), [
    ("Spine", (0, 10, 0), [
        ("Spine1", (0, 14, 0), [
            ("Neck", (0, 17, 0), [
                ("Head", (0, 10, 0), [("End Site", (0, 18, 0), None)]),
            ]),
            ("LeftShoulder", (4, 13, 0), [
                ("LeftArm", (13, 0, 0), [
                    ("LeftForeArm", (0, -28, 0), [
                        ("LeftHand", (0, -24, 0), [("End Site", (0, -17, 0), None)]),
                    ]),
                ]),
            ]),
            ("RightShoulder", (-4, 13, 0), [
                ("RightArm", (-13, 0, 0), [
                    ("RightForeArm", (0, -28, 0), [
                        ("RightHand", (0, -24, 0), [("End Site", (0, -17, 0), None)]),
                    ]),
                ]),
            ]),
        ]),
    ]),
    ("LeftUpLeg", (9, -4, 0), [
        ("LeftLeg", (0, -42, 0), [
            ("LeftFoot", (0, -40, 0), [
                ("LeftToeBase", (0, -6, 13), [("End Site", (0, -2, 6), None)]),
            ]),
        ]),
    ]),
    ("RightUpLeg", (-9, -4, 0), [
        ("RightLeg", (0, -42, 0), [
            ("RightFoot", (0, -40, 0), [
                ("RightToeBase", (0, -6, 13), [("End Site", (0, -2, 6), None)]),
            ]),
        ]),
    ]),
])

JOINT_ORDER = ["Hips", "Spine", "Spine1", "Neck", "Head",
               "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
               "RightShoulder", "RightArm", "RightForeArm", "RightHand",
               "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
               "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase"]

def clampa(v, lim=28.0):
    return max(-lim, min(lim, v))

def build_frame(f):
    # --- root ---
    osc = OSC_YAW(f)
    yaw_path = PATH_YAW(f)
    yaw = yaw_path + osc
    lean = ROOT_PITCH(f)
    roll = ROLL(f)
    Rroot = ry(yaw) @ rx(lean) @ rz(roll)
    pos = np.array([HIP_X(f), HIP_Y(f), HIP_Z(f)])
    if T_TAKEOFF <= f <= T_LAND:
        t = (f - T_TAKEOFF) * DT
        pos[1] = 1.00 + V0_JUMP * t - G * t * t
    pos = pos + ry(yaw_path) @ np.array([SWAY(f), 0.0, 0.0])
    breath = 0.0
    if f >= 195:
        b = min(1.0, (f - 195) / 25.0)
        ph = 2.0 * math.pi * 0.3 * (f - 195) * DT
        pos[1] += 0.004 * b * math.sin(ph)
        breath = 1.2 * b * math.sin(ph)

    rots = {}
    # --- trunk / head ---
    spx = SPINE_X(f)
    lead = CHEST_LEAD(f)
    look = LOOK(f)
    counter = -0.6 * (lean + 1.1 * spx)
    rots["Spine"]  = ry(-0.25 * osc + 0.35 * lead) @ rx(0.6 * spx)
    rots["Spine1"] = ry(-0.45 * osc + 0.65 * lead) @ rx(0.5 * spx + breath)
    rots["Neck"]   = ry(0.4 * look) @ rx(clampa(0.45 * counter))
    rots["Head"]   = ry(0.6 * look) @ rx(clampa(0.55 * counter))
    # --- arms ---
    ab = ABD(f)
    rots["LeftShoulder"]  = rz(3.0)
    rots["RightShoulder"] = rz(-3.0)
    rots["LeftArm"]  = rx(ARM_L(f)) @ rz(ab)
    rots["RightArm"] = rx(ARM_R(f)) @ rz(-ab)
    rots["LeftForeArm"]  = rx(ELBOW(f))
    rots["RightForeArm"] = rx(ELBOW(f))
    rots["LeftHand"]  = rx(-8.0)
    rots["RightHand"] = rx(-8.0)
    # --- legs (IK) ---
    for side, plants, hoff in (("Left", L_PLANTS, HIPJ_L),
                               ("Right", R_PLANTS, HIPJ_R)):
        ank, fp, fy, toe = foot_state(plants, f)
        hipw = pos + Rroot @ hoff
        pole = ry(0.5 * (yaw + fy)) @ np.array([0.0, 0.0, 1.0])
        A_th, A_kn, A_sh = solve_leg(hipw, ank, Rroot, pole)
        R_foot_des = ry(fy) @ rx(fp)
        R_foot = (Rroot @ A_sh).T @ R_foot_des
        rots[side + "UpLeg"] = A_th
        rots[side + "Leg"] = A_kn
        rots[side + "Foot"] = R_foot
        rots[side + "ToeBase"] = rx(toe)

    vals = [pos[0] * M, pos[1] * M, pos[2] * M]
    z, x, y = zxy_from_matrix(Rroot)
    vals += [z, x, y]
    for name in JOINT_ORDER[1:]:
        z, x, y = zxy_from_matrix(rots[name])
        vals += [z, x, y]
    assert len(vals) == 66
    return vals

# ----------------------------------------------------------------------------
# BVH writer
# ----------------------------------------------------------------------------
def write_hierarchy(node, depth, lines, is_root):
    name, off, children = node
    ind = "\t" * depth
    if name == "End Site":
        lines.append(ind + "End Site")
        lines.append(ind + "{")
        lines.append(ind + "\tOFFSET %.4f %.4f %.4f" % off)
        lines.append(ind + "}")
        return
    kw = "ROOT" if is_root else "JOINT"
    lines.append(ind + "%s %s" % (kw, name))
    lines.append(ind + "{")
    lines.append(ind + "\tOFFSET %.4f %.4f %.4f" % off)
    if is_root:
        lines.append(ind + "\tCHANNELS 6 Xposition Yposition Zposition "
                           "Zrotation Xrotation Yrotation")
    else:
        lines.append(ind + "\tCHANNELS 3 Zrotation Xrotation Yrotation")
    for ch in children:
        write_hierarchy(ch, depth + 1, lines, False)
    lines.append(ind + "}")

def main():
    lines = ["HIERARCHY"]
    write_hierarchy(SKEL, 0, lines, True)
    lines.append("MOTION")
    lines.append("Frames: %d" % N)
    lines.append("Frame Time: %.7f" % DT)
    for f in range(N):
        vals = build_frame(f)
        lines.append(" ".join("%.4f" % v for v in vals))
    text = "\n".join(lines) + "\n"
    with open(OUT_BVH, "w") as fh:
        fh.write(text)
    # well-formedness summary (format only)
    motion_lines = lines[-N:]
    counts = {len(l.split()) for l in motion_lines}
    print("wrote", OUT_BVH)
    print("frames:", N, " duration: %.3f s" % (N * DT))
    print("joints:", len(JOINT_ORDER), " channels/frame:", sorted(counts))

if __name__ == "__main__":
    main()
