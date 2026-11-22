"""Generate README animated preview GIF and 10-pose showcase banner."""

import math
from pathlib import Path
import sys

from PIL import Image, ImageDraw
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from pet.live_deformer import ProneIdleRig

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
DOCS_DIR = ROOT / "docs"


def qpixmap_to_pil(pix) -> Image.Image:
    qim = pix.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = qim.width(), qim.height()
    return Image.frombuffer("RGBA", (w, h), bytes(qim.constBits()), "raw", "RGBA", 0, 1).copy()


def build_live_gif() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    faces = {
        k: Image.open(ASSETS_DIR / f"{k}.png").convert("RGBA")
        for k in ("idle", "idle_half", "idle_closed", "idle_happy", "idle_talk")
    }
    rig = ProneIdleRig(faces, 360, 261, dpr=1.0)

    frames: list[Image.Image] = []
    total_frames = 44
    fps = 14
    for i in range(total_frames):
        t = i / fps
        # Timeline: 0..1.3s open+blink, 1.3..2.2s happy petting blush, 2.2..3.1s open+ear twitch
        if 0.45 <= t < 0.55 or 0.72 <= t < 0.82:
            face = "idle_half"
            iris = 0.3
        elif 0.55 <= t < 0.72:
            face = "idle_closed"
            iris = 0.0
        elif 1.35 <= t < 2.35:
            face = "idle_happy"
            iris = 0.0
        else:
            face = "idle"
            iris = 1.0

        tail1 = math.sin(t * 3.0) * 0.85
        tail2 = math.cos(t * 3.0 - 0.55) * 0.85
        feet = math.sin(t * 4.2) * 0.75
        foot_l = math.sin(t * 4.2 + 0.8) * 0.75
        foot_r = math.sin(t * 4.2 + 3.6) * 0.75
        ear_l = 0.75 if 0.9 <= t <= 1.15 else (0.4 if 1.35 <= t < 2.35 else 0.0)
        ear_r = 0.75 if 2.4 <= t <= 2.65 else (0.4 if 1.35 <= t < 2.35 else 0.0)
        ahoge = math.sin(t * 3.5) * 0.55
        breath = math.sin(t * 2.4)
        look_x = math.sin(t * 1.8) * 0.7
        look_y = math.cos(t * 1.4) * 0.3
        breeze = math.sin(t * 2.0) * 0.75

        pix = rig.render(
            face, tail1, tail2, feet, foot_l, foot_r,
            ear_l, ear_r, ahoge, breath, look_x, look_y, iris, breeze,
        )
        fg = qpixmap_to_pil(pix)
        bg = Image.new("RGBA", fg.size, (22, 20, 36, 255))
        bg.alpha_composite(fg)
        frames.append(bg.convert("P", palette=Image.Palette.ADAPTIVE, colors=256))

    out_gif = DOCS_DIR / "preview_live.gif"
    frames[0].save(
        out_gif,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / fps),
        loop=0,
        optimize=True,
    )
    print(f"Saved {out_gif} ({out_gif.stat().st_size // 1024} KB)")


def build_poses_showcase() -> None:
    pose_order = [
        "idle", "nap", "side_sleep", "stretch", "purr",
        "groom", "pounce", "shy", "sleepy", "drag",
    ]
    cols, rows = 5, 2
    cell_w, cell_h = 260, 300
    canvas = Image.new("RGBA", (cols * cell_w, rows * cell_h), (22, 20, 36, 255))
    draw = ImageDraw.Draw(canvas)

    for idx, name in enumerate(pose_order):
        path = ASSETS_DIR / f"{name}.png"
        if not path.exists():
            continue
        im = Image.open(path).convert("RGBA")
        im.thumbnail((cell_w - 24, cell_h - 24), Image.Resampling.LANCZOS)
        r, c = divmod(idx, cols)
        ox = c * cell_w + (cell_w - im.width) // 2
        oy = r * cell_h + (cell_h - im.height) // 2
        canvas.alpha_composite(im, (ox, oy))
        draw.rounded_rectangle(
            [c * cell_w + 6, r * cell_h + 6, (c + 1) * cell_w - 6, (r + 1) * cell_h - 6],
            radius=14,
            outline=(140, 115, 220, 65),
            width=1,
        )

    out_png = DOCS_DIR / "poses_showcase.png"
    canvas.convert("RGB").save(out_png, optimize=True)
    print(f"Saved {out_png} ({out_png.stat().st_size // 1024} KB)")


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    build_live_gif()
    build_poses_showcase()


if __name__ == "__main__":
    main()
