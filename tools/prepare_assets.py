"""Build all 10 cat-trait HD transparent PNG assets from chroma-key green-screen sources."""

from pathlib import Path
from PIL import Image

from tools.matting import crop_tight, matte_green_screen

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
ARTIFACT_DIR = Path(
    r"C:\Users\samuel\.gemini\antigravity\brain\ef674b7c-fb51-4908-8f3c-c5b4c6f653c4"
)

HD_SOURCES: dict[str, Path] = {
    "idle": ARTIFACT_DIR / "pose_thinking_prone_1795287697797.jpg",
    "happy": ARTIFACT_DIR / "cute_happy_v2_1795286829445.jpg",
    "purr": ARTIFACT_DIR / "cat_purr_v2_1795288414966.jpg",
    "groom": ARTIFACT_DIR / "cat_groom_1795288369814.jpg",
    "pounce": ARTIFACT_DIR / "cat_pounce_1795288380502.jpg",
    "shy": ARTIFACT_DIR / "pose_shy_kneel_1795287700058.jpg",
    "sleepy": ARTIFACT_DIR / "cute_sleepy_1795286782479.jpg",
    "stretch": ARTIFACT_DIR / "pose_stretch_1795287759125.jpg",
    "drag": ARTIFACT_DIR / "cute_drag_1795286797972.jpg",
}


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    scratch = ARTIFACT_DIR / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    matted: dict[str, Image.Image] = {}
    for name, src_path in HD_SOURCES.items():
        if not src_path.exists():
            print(f"Missing source: {src_path}")
            continue
        im = Image.open(src_path)
        # Tighter threshold for pounce so the soft glow around the star toy stays crisp without green halo
        if name == "pounce":
            rgba = crop_tight(matte_green_screen(im, t_low=0.06, t_high=0.22), pad=12)
        else:
            rgba = crop_tight(matte_green_screen(im), pad=12)
        matted[name] = rgba
        out_path = ASSETS_DIR / f"{name}.png"
        rgba.save(out_path)
        print(f"Saved {out_path.name}: {rgba.size}")

    # Save a 2x5 dark-background QA contact sheet of all 10 cat-trait poses
    cols = 5
    thumb_w, thumb_h = 300, 420
    names = list(matted.keys())
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * thumb_w, rows * thumb_h), (24, 22, 36, 255))
    for idx, name in enumerate(names):
        im = matted[name].copy()
        im.thumbnail((thumb_w - 18, thumb_h - 18), Image.Resampling.LANCZOS)
        r, c = divmod(idx, cols)
        ox = c * thumb_w + (thumb_w - im.width) // 2
        oy = r * thumb_h + (thumb_h - im.height) // 2
        sheet.alpha_composite(im, (ox, oy))
    qa_path = scratch / "qa_10poses_dark.png"
    sheet.convert("RGB").save(qa_path)
    print(f"Saved QA sheet: {qa_path}")


if __name__ == "__main__":
    main()
