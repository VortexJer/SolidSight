---
name: animationsight
description: "Use whenever the user asks to review, debug, validate, compare — or EDIT/fix — an animation clip or mocap take (.bvh): foot sliding, pops, ground penetration, balance, timing, loop seams. You cannot watch an animation; this tool turns it into exact numbers plus renders of the exact frames that are wrong, and can load, modify and re-write the clip (parse_bvh -> save_bvh)."
---

# /animationsight

An animation is judged by watching it. You cannot watch it. So measure
it: velocities, accelerations, jerk, angular rates, contact events, foot
sliding, balance against the support base, ground penetration,
smoothness and loop continuity — plus PNG renders of the exact frames
the findings point at.

The loop is: inspect -> read the checks -> LOOK at the flagged frames ->
fix the clip -> inspect again -> `diff` to prove what changed.

## Usage

```
animationsight inspect walk.bvh                  # report.json + evidence frames + tracks
animationsight inspect walk.bvh --out DIR        # output dir (default: ./out)
animationsight inspect walk.bvh --unit cm        # what the file's numbers mean (mm|cm|m|in)
animationsight inspect walk.bvh --up y           # vertical axis (x|y|z; BVH convention is y)
animationsight inspect walk.bvh --floor 0        # declare the floor instead of inferring it
animationsight inspect walk.bvh --frames 10      # evenly spaced renders (flagged frames always added)
animationsight inspect walk.bvh --view side      # side|front|top
animationsight inspect walk.bvh --kind oneshot   # declare intent: oneshot (jump, hit) | loop | auto
animationsight inspect walk.bvh --json           # full report JSON on stdout

animationsight diff take_a.bvh take_b.bvh --kind oneshot   # what changed: peaks, findings appeared/gone
animationsight track walk.bvh LeftFoot           # one joint's per-frame position + speed
animationsight version
```

Exit codes: 0 ok, 1 bad clip / bad argument, 2 a FAIL-level finding
(ground penetration).

## What You Must Do When Invoked

### Step 0 - Install

```bash
animationsight version || pip install "git+https://github.com/VortexJer/AISight#subdirectory=animationsight"
```

### Step 1 - Declare the units and the up axis. Do not guess.

BVH files do not record what their numbers mean. `--unit cm` is the
mocap default and `--up y` is the BVH convention, but if the report's
COM height comes out as 92 mm or 9200 mm for a human, the unit is wrong
— a human's COM sits around 900-1100 mm. Check that number first, every
time. Everything downstream (speeds, slip distances, thresholds) is
wrong if the unit is wrong.

### Step 2 - Inspect, then read the checks

```bash
animationsight inspect walk.bvh
```

Every finding carries `where` (the frame, the joint, the magnitude) and
a `try:`. The check ids:

| id | level | means |
|---|---|---|
| `ground-penetration` | FAIL | a joint went through the floor. Never intentional. |
| `foot-sliding` | warn | a planted foot drifts — "skating". The classic defect, and nearly invisible frame by frame. |
| `motion-pop` | warn | discontinuity events, clustered: a "pose snap" hits many joints in one frame (blocking pass, splice — needs inbetweens), a "joint pop" is one bad key. |
| `floaty-flight` / `heavy-flight` | warn | during flight the COM must fall at 1 g; the report gives the measured ratio and the exact fix (T = 2*sqrt(2h/g)). Nobody can SEE 0.68 g — it just feels off. |
| `gravity-unit-suspect` | warn | effective gravity ~0.1x or ~10x = the --unit is probably wrong (one metric prefix), not the animation. |
| `root-on-rails` | warn | airborne but the COM never falls: both feet leave the ground while the root glides — a driven root, not a jump. Drop it ballistically (h = g*(T/2)^2/2) or keep a foot planted. |
| `loop-discontinuity` | warn | the seam jumps much more than a normal frame does. Declare `--kind oneshot` to silence it for jumps/hits/gestures. |
| `com-weights-unknown` | warn | joint names were unrecognisable, so the COM used uniform weights. Balance numbers are then indicative, not exact. |

### Step 3 - LOOK at the flagged frames

`inspect` renders the evenly spaced frames AND every frame a finding
points at, with the offending joint circled and the COM drawn. The full
COM trajectory is in `out/com_trajectory.csv` (report.json keeps the
summary only — read the CSV when you need per-frame numbers). Open them
with the Read tool. The tracks (`track_com_height.png`,
`track_foot_speed.png`) show the time series with the flagged frames
marked — that is where a defect's shape is visible: one spike vs a
sustained drift.

### Step 4 - Interpret honestly

- **Ballistics is the strongest single check for jumps**: during an
  airborne span the COM has no choice but 1 g. `ballistics.flights[]`
  gives each flight's effective gravity ratio, apex and duration. 1.0
  is physical; a deliberate stylised float is fine — but then SAY it is
  stylised, with the number.

- **Balance**: `com_to_support_mm` is the distance from the COM's ground
  projection to the support base. Big numbers during `airborne_frames`
  are not a defect — running is supposed to be out of balance. Read the
  two together.
- **Foot sliding**: `total_slip_mm` is the accumulated drift while
  planted. A few mm is noise; tens of mm is skating.
- **The floor** is inferred (10th percentile of the per-frame lowest
  point) unless you declare it. Never inferred from the clip's minimum:
  a penetration defect would then define the floor and hide itself.
  If the report's floor looks wrong, pass `--floor`.
- **Peak speeds** are per joint, with the frame. Quote them; do not say
  "the motion looks fast".

### Step 5 - Fix, re-inspect, diff

```bash
animationsight diff before.bvh after.bvh
```
Lists peak-speed changes per joint and findings that appeared or
disappeared. Use it to prove your fix did what you meant and nothing
else.

### Editing an existing clip

You are not limited to reviewing: `parse_bvh` -> modify -> `save_bvh`
is the edit loop for clips someone hands you.

```python
from animationsight import parse_bvh, save_bvh
clip = parse_bvh("walk.bvh", unit="cm")
clip.frames[:, 1] += 2.0        # raw channel values, file units
# joints: clip.joints (depth-first); channel layout: j.chan_start
save_bvh(clip, "walk_fixed.bvh")
```

Then `inspect` the result — an edit without a re-inspect is a claim.

### Showing the human

`report.json` and the renders are YOUR interface; the person you work
for gets a browser page. **ALWAYS end a commission's FINAL run with
`--show`** (or run `animationsight preview out/`) — it builds
`out/index.html` (verdict + every render, GIFs first) and opens it in
their browser. Not optional, and they should not have to ask; one
popup per commission (skip it on intermediate iterations). Never use
it for yourself.

## Honesty Rules

- A commission that names a SPECIFIC real thing (a particular character, vehicle, device, board) without its identifying details: ask which exact one BEFORE working — never substitute your invented average of the category.
- Never say a clip "looks good". Say what was measured and what the
  numbers were.
- The COM is only as good as the joint names: if
  `anthropometric_weights` is false, say so before quoting balance.
- A clip is not reviewed until you have LOOKED at the flagged frames.
- If the request needs something this does not measure (facial rigs,
  blend shapes, IK/FK graph structure, physics sim), say so plainly
  instead of implying it was checked.

## Scope

Reads: BVH (skeletal mocap/animation clips).
Measures: kinematics, contacts, balance, smoothness, loops.
Does NOT do: rendering the character, blend shapes/facial rigs,
retargeting, or physics simulation. Editing is on you, with the
tool's own halves: `parse_bvh` -> modify -> `save_bvh` -> re-inspect
(or fix the clip in the DCC tool that made it).

For 3D geometry (parts, assemblies, robots, URDF/collision sweeps), that
is `solidsight` — a sibling tool with the same philosophy.
