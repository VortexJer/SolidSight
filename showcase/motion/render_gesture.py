"""Render Vigia PERFORMING the gesture: the real 3D robot, posed by the
same servo profile the BVH carries, assembled into a GIF.

The skeleton clip is the review substrate (animationsight measures it);
this is the presentation layer: solidsight renders vigia.build() at each
sampled pose. One process, deterministic.

Run: python render_gesture.py   ->  gesture_eased.gif, gesture_stepped.gif
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[0] / "robot"))

from make_gesture import DURATION, angles_at  # noqa: E402

from solidsight import scene as scene_mod  # noqa: E402
from solidsight.render import render_view  # noqa: E402
from solidsight.scene import Scene  # noqa: E402

N_FRAMES = 22
SIZE = 460


def render(eased: bool, out_name: str) -> None:
    import vigia
    frames = []
    for i in range(N_FRAMES):
        t = DURATION * i / (N_FRAMES - 1)
        head, al, ar = angles_at(t, eased)
        sc = Scene()
        scene_mod.activate(sc)
        try:
            vigia.build(head=head, arm_l=al, arm_r=ar, joints=False)
            img = render_view(sc, "iso", size=SIZE, title="VIGIA",
                              subtitle=f"{'eased' if eased else 'stepped'}"
                                       f" servo profile - t={t:.2f}s")
        finally:
            scene_mod.deactivate()
        frames.append(img)
        print(f"  frame {i + 1}/{N_FRAMES}  head={head:.0f} "
              f"arm_l={al:.0f}", flush=True)

    ms = int(1000 * DURATION / N_FRAMES)
    frames[0].save(HERE / out_name, save_all=True,
                   append_images=frames[1:], duration=ms, loop=0,
                   optimize=True)
    print(f"wrote {out_name}")


if __name__ == "__main__":
    render(True, "gesture_eased.gif")
    render(False, "gesture_stepped.gif")
