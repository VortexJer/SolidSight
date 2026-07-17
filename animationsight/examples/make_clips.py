"""Generate the example clips.

These are SYNTHETIC and that is deliberate: a clip whose ground truth is
known by construction is the only kind that can prove a measurement is
right. Real mocap has unknown defects; here we know every one.

The walk is built the way animators build one: the FOOT's world
trajectory is authored first (stance = planted, swing = an arc), and the
leg angles are solved by inverse kinematics to hit it. A walk written as
naive sinusoids does NOT plant its feet — the first version of this file
did exactly that, and animationsight caught it (every frame slid; see
examples/01-walk/README.md).

  walk_clean.bvh   the reference: feet planted, matched stride
  walk_broken.bvh  three injected defects with exact magnitudes:
                     * foot sliding: root travels 15 % faster than stride
                     * a pop: one frame of the left arm displaced 26 deg
                     * ground penetration: right foot dips 90 mm, frames 22-26

Run: python make_clips.py
"""

from __future__ import annotations

import math
from pathlib import Path

FPS = 30.0
CYCLES = 3
FRAMES_PER_CYCLE = 40
N = CYCLES * FRAMES_PER_CYCLE

# --- skeleton (cm, Y-up, forward = +Z) -------------------------------------
THIGH, SHIN = 42.0, 40.0          # segment lengths (82 cm of leg)
ANKLE_H = 6.0                     # ankle height when the foot is flat
# Hip height is NOT free: at the extremes of stance the foot is STEP/2
# ahead/behind, so the hip-to-ankle distance is hypot(HIP_Y - ANKLE_H,
# STEP/2) and that must stay under THIGH + SHIN with room for the
# injected dip. 88 cm silently clamped the IK (leg needed 91 of 82) and
# the "penetration" defect never happened — assert_reachable() below now
# makes that impossible to miss.
HIP_Y = 80.0
STRIDE = 60.0                     # cm the body advances per cycle
STEP = STRIDE / 2.0               # each foot travels a full stride per cycle,
                                  # in half the time (the other half it is
                                  # planted) -> hip speed = STRIDE/cycle
SWING_LIFT = 9.0                  # peak toe clearance during swing
HIP_BOB = 1.6
DIP = 4.0                         # injected penetration depth (broken clip)

HIERARCHY = """HIERARCHY
ROOT Hips
{
  OFFSET 0.00 0.00 0.00
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  JOINT Spine
  {
    OFFSET 0.00 12.00 0.00
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT Chest
    {
      OFFSET 0.00 14.00 0.00
      CHANNELS 3 Zrotation Xrotation Yrotation
      JOINT Neck
      {
        OFFSET 0.00 18.00 0.00
        CHANNELS 3 Zrotation Xrotation Yrotation
        JOINT Head
        {
          OFFSET 0.00 8.00 0.00
          CHANNELS 3 Zrotation Xrotation Yrotation
          End Site
          {
            OFFSET 0.00 10.00 0.00
          }
        }
      }
      JOINT LeftUpperArm
      {
        OFFSET 8.00 14.00 0.00
        CHANNELS 3 Zrotation Xrotation Yrotation
        JOINT LeftForearm
        {
          OFFSET 0.00 -26.00 0.00
          CHANNELS 3 Zrotation Xrotation Yrotation
          JOINT LeftHand
          {
            OFFSET 0.00 -24.00 0.00
            CHANNELS 3 Zrotation Xrotation Yrotation
            End Site
            {
              OFFSET 0.00 -8.00 0.00
            }
          }
        }
      }
      JOINT RightUpperArm
      {
        OFFSET -8.00 14.00 0.00
        CHANNELS 3 Zrotation Xrotation Yrotation
        JOINT RightForearm
        {
          OFFSET 0.00 -26.00 0.00
          CHANNELS 3 Zrotation Xrotation Yrotation
          JOINT RightHand
          {
            OFFSET 0.00 -24.00 0.00
            CHANNELS 3 Zrotation Xrotation Yrotation
            End Site
            {
              OFFSET 0.00 -8.00 0.00
            }
          }
        }
      }
    }
  }
  JOINT LeftThigh
  {
    OFFSET 9.00 0.00 0.00
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT LeftShin
    {
      OFFSET 0.00 -42.00 0.00
      CHANNELS 3 Zrotation Xrotation Yrotation
      JOINT LeftFoot
      {
        OFFSET 0.00 -40.00 0.00
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
          OFFSET 0.00 -6.00 0.00
        }
      }
    }
  }
  JOINT RightThigh
  {
    OFFSET -9.00 0.00 0.00
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT RightShin
    {
      OFFSET 0.00 -42.00 0.00
      CHANNELS 3 Zrotation Xrotation Yrotation
      JOINT RightFoot
      {
        OFFSET 0.00 -40.00 0.00
        CHANNELS 3 Zrotation Xrotation Yrotation
        End Site
        {
          OFFSET 0.00 -6.00 0.00
        }
      }
    }
  }
}
"""

JOINTS = [
    ("Hips", 6), ("Spine", 3), ("Chest", 3), ("Neck", 3), ("Head", 3),
    ("LeftUpperArm", 3), ("LeftForearm", 3), ("LeftHand", 3),
    ("RightUpperArm", 3), ("RightForearm", 3), ("RightHand", 3),
    ("LeftThigh", 3), ("LeftShin", 3), ("LeftFoot", 3),
    ("RightThigh", 3), ("RightShin", 3), ("RightFoot", 3),
]


def hip_z_at(f: int, speed_scale: float = 1.0) -> float:
    return STRIDE * speed_scale * (f / FRAMES_PER_CYCLE)


class UnreachableFoot(Exception):
    """The IK was asked for a pose the leg cannot make.

    This is an error, not something to clamp away: a clamped target
    means the generated clip is not the clip that was authored, and
    every measurement downstream would describe a pose nobody chose.
    """


def leg_ik(hip_y: float, hip_z: float, foot_y: float,
           foot_z: float) -> tuple[float, float]:
    """Solve the 2-link leg. Returns (thigh_x_channel, shin_x_channel)
    in degrees for this file's hierarchy.

    Sign convention, derived from the hierarchy (leg hangs -Y, X-rotation
    acts in the YZ plane): a POSITIVE Xrotation swings the limb toward
    -Z, so forward (+Z) reach needs a NEGATIVE thigh angle, and knee
    flexion (heel toward the seat, -Z) is POSITIVE on the shin.
    """
    dz, dy = foot_z - hip_z, foot_y - hip_y
    L = math.hypot(dz, dy)
    if L > THIGH + SHIN - 0.5:
        raise UnreachableFoot(
            f"foot target needs {L:.1f} cm of leg but there is "
            f"{THIGH + SHIN:.1f} (hip y={hip_y:.1f} z={hip_z:.1f} -> "
            f"foot y={foot_y:.1f} z={foot_z:.1f}). Lower HIP_Y, shorten "
            f"STRIDE, or reduce the injected dip.")

    # interior angle at the knee (180 deg = straight)
    cos_knee = (THIGH ** 2 + SHIN ** 2 - L ** 2) / (2 * THIGH * SHIN)
    knee_interior = math.degrees(math.acos(max(-1.0, min(1.0, cos_knee))))
    flexion = 180.0 - knee_interior

    # hip: direction to the foot, plus the triangle's angle at the hip
    alpha = math.degrees(math.atan2(dz, -dy))        # +ve = foot is forward
    cos_beta = (THIGH ** 2 + L ** 2 - SHIN ** 2) / (2 * THIGH * L)
    beta = math.degrees(math.acos(max(-1.0, min(1.0, cos_beta))))

    return -(alpha + beta), flexion


def pose(f: int, broken: bool) -> list[float]:
    speed_scale = 1.15 if broken else 1.0        # 15 % too fast = sliding
    t = 2 * math.pi * f / FRAMES_PER_CYCLE
    hip_z = hip_z_at(f, speed_scale)
    hip_y = HIP_Y + HIP_BOB * math.cos(2 * t)

    vals: dict[str, list[float]] = {}
    vals["Hips"] = [0.0, hip_y, hip_z, 0.0, 0.0, 0.0]
    vals["Spine"] = [0.0, 2.0 * math.sin(t), 0.0]
    vals["Chest"] = [0.0, 1.0, 0.0]
    vals["Neck"] = [0.0, 0.0, 0.0]
    vals["Head"] = [0.0, 0.0, 0.0]

    arm = 18.0 * math.sin(t)
    la = arm + (26.0 if (broken and f == 47) else 0.0)      # one-frame pop
    vals["LeftUpperArm"] = [0.0, -la, 0.0]
    vals["LeftForearm"] = [0.0, -max(0.0, 12.0 * math.sin(t)), 0.0]
    vals["LeftHand"] = [0.0, 0.0, 0.0]
    vals["RightUpperArm"] = [0.0, arm, 0.0]
    vals["RightForearm"] = [0.0, -max(0.0, -12.0 * math.sin(t)), 0.0]
    vals["RightHand"] = [0.0, 0.0, 0.0]

    for side, ph_off in (("Left", 0.0), ("Right", 0.5)):
        # this foot's phase within its own cycle (0..0.5 stance, 0.5..1 swing)
        ph = ((f / FRAMES_PER_CYCLE) + ph_off) % 1.0

        # The foot is authored RELATIVE TO THE HIP, then the hip's world
        # position carries it. That is how a real rig works, and it is
        # what makes sliding injectable honestly: STEP/STRIDE below are
        # the ANIMATION's stride; the hip travels speed_scale x that.
        # When the two agree the stance foot is world-stationary; when
        # the root is driven faster, the planted foot drifts — exactly
        # the engine-side bug this measures.
        if ph < 0.5:
            # STANCE: starts STEP/2 ahead of the hip, ends STEP/2 behind
            fz = hip_z + STEP / 2.0 - STRIDE * ph
            fy = ANKLE_H
        else:
            # SWING: back to front, smoothstep in z (no jerk at the
            # hand-offs), sine arc in y
            s = (ph - 0.5) / 0.5
            e = s * s * (3.0 - 2.0 * s)
            fz = hip_z - STEP / 2.0 + STEP * e
            fy = ANKLE_H + SWING_LIFT * math.sin(math.pi * s)

        if broken and side == "Right" and 22 <= f <= 26:
            fy -= DIP                                  # dip through the floor

        th, sh = leg_ik(hip_y, hip_z, fy, fz)
        vals[f"{side}Thigh"] = [0.0, th, 0.0]
        vals[f"{side}Shin"] = [0.0, sh, 0.0]
        # keep the foot flat: undo the leg's accumulated pitch
        vals[f"{side}Foot"] = [0.0, -(th + sh), 0.0]

    row: list[float] = []
    for name, n in JOINTS:
        v = vals[name]
        assert len(v) == n, name
        row += v
    return row


def write(path: Path, broken: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [HIERARCHY, "MOTION", f"Frames: {N}",
             f"Frame Time: {1.0 / FPS:.6f}"]
    for f in range(N):
        lines.append(" ".join(f"{v:.4f}" for v in pose(f, broken)))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path.name}: {N} frames @ {FPS} fps"
          + ("  [3 injected defects]" if broken else "  [reference]"))


if __name__ == "__main__":
    here = Path(__file__).parent
    print(f"stride {STRIDE} cm/cycle -> "
          f"{STRIDE / (FRAMES_PER_CYCLE / FPS):.1f} cm/s")
    write(here / "01-walk" / "walk_clean.bvh", broken=False)
    write(here / "01-walk" / "walk_broken.bvh", broken=True)
