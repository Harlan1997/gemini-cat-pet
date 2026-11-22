"""Register and seamlessly blend face-only variants onto assets/idle.png (zero flicker)."""

from pathlib import Path
import cv2
import numpy as np
from PIL import Image

from tools.matting import crop_tight, matte_green_screen

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
ARTIFACT_DIR = Path(
    r"C:\Users\samuel\.gemini\antigravity\brain\ef674b7c-fb51-4908-8f3c-c5b4c6f653c4"
)

BASE_SRC = ARTIFACT_DIR / "pose_thinking_prone_1795287697797.jpg"
FACE_VARIANTS: dict[str, Path] = {
    "idle_half": ARTIFACT_DIR / "idle_face_half_1795291210968.jpg",
    "idle_closed": ARTIFACT_DIR / "idle_face_closed_1795291220910.jpg",
    "idle_happy": ARTIFACT_DIR / "idle_face_happy_1795291231843.jpg",
    "idle_talk": ARTIFACT_DIR / "idle_face_talk_1795291246239.jpg",
}


def compute_crop_bbox(src_path: Path, pad: int = 12) -> tuple[int, int, int, int]:
    """Return the exact crop box used to produce assets/idle.png from BASE_SRC."""
    im = Image.open(src_path)
    matted = matte_green_screen(im)
    bbox = matted.getbbox()
    w, h = matted.size
    return (
        max(0, bbox[0] - pad),
        max(0, bbox[1] - pad),
        min(w, bbox[2] + pad),
        min(h, bbox[3] + pad),
    )


def build_soft_face_mask(h: int, w: int, include_cheeks: bool = False) -> np.ndarray:
    """Create a smooth feathered mask covering ONLY eyes + mouth (+ optional rosy cheeks)."""
    mask = np.zeros((h, w), dtype=np.float32)

    # Measured on 1110x804 idle.png:
    # Left eye:  center ~(236, 358), radii ~(44, 34)
    # Right eye: center ~(338, 352), radii ~(48, 34)
    # Mouth:     center ~(284, 422), radii ~(34, 24)
    # Cheeks:    slightly wider around (228, 390) & (348, 384)
    sx, sy = w / 1110.0, h / 804.0

    def add_ellipse(cx: float, cy: float, rx: float, ry: float) -> None:
        cv2.ellipse(
            mask,
            (int(round(cx * sx)), int(round(cy * sy))),
            (int(round(rx * sx)), int(round(ry * sy))),
            0,
            0,
            360,
            1.0,
            -1,
        )

    add_ellipse(234, 357, 42, 34)  # left eye
    add_ellipse(338, 351, 46, 34)  # right eye
    add_ellipse(284, 421, 34, 24)  # mouth

    if include_cheeks:
        add_ellipse(235, 382, 46, 26)
        add_ellipse(340, 376, 48, 26)
        add_ellipse(286, 418, 42, 28)

    # Smooth Gaussian feather for invisible seam blending
    k = max(15, int(round(27 * sx)) | 1)
    mask = cv2.GaussianBlur(mask, (k, k), 0)
    return np.clip(mask, 0.0, 1.0)


def align_variant_to_base(base_rgb: np.ndarray, var_rgb: np.ndarray) -> np.ndarray:
    """Sub-pixel align variant to base using ECC translation on the head/hair frame."""
    h, w = base_rgb.shape[:2]
    # Use forehead/hair/hands region around face (x: 100..470, y: 120..500)
    x0, x1 = int(w * 0.10), int(w * 0.44)
    y0, y1 = int(h * 0.15), int(h * 0.62)

    g_base = cv2.cvtColor(base_rgb[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY).astype(np.float32)
    g_var = cv2.cvtColor(var_rgb[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY).astype(np.float32)

    warp = np.eye(2, 3, dtype=np.float32)
    try:
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5)
        cv2.findTransformECC(g_base, g_var, warp, cv2.MOTION_TRANSLATION, criteria)
    except cv2.error:
        pass

    dx, dy = float(warp[0, 2]), float(warp[1, 2])
    print(f"  ECC alignment shift: dx={dx:.2f}px, dy={dy:.2f}px")
    aligned = cv2.warpAffine(
        var_rgb,
        warp,
        (w, h),
        flags=cv2.INTER_LANCZOS4 + cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return aligned


def main() -> None:
    crop_box = compute_crop_bbox(BASE_SRC, pad=12)
    base_rgba = np.asarray(Image.open(ASSETS_DIR / "idle.png").convert("RGBA"), dtype=np.uint8)
    h, w = base_rgba.shape[:2]
    base_rgb = base_rgba[:, :, :3]
    base_a = base_rgba[:, :, 3:4]

    scratch = ARTIFACT_DIR / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    thumbs: list[Image.Image] = []

    for name, src_path in FACE_VARIANTS.items():
        if not src_path.exists():
            print(f"Missing {src_path}")
            continue
        print(f"Processing {name}...")
        var_full = Image.open(src_path).convert("RGB")
        if var_full.size != Image.open(BASE_SRC).size:
            var_full = var_full.resize(Image.open(BASE_SRC).size, Image.Resampling.LANCZOS)
        var_crop = np.asarray(var_full.crop(crop_box), dtype=np.uint8)
        if var_crop.shape[:2] != (h, w):
            var_crop = cv2.resize(var_crop, (w, h), interpolation=cv2.INTER_LANCZOS4)

        aligned_rgb = align_variant_to_base(base_rgb, var_crop)
        mask = build_soft_face_mask(h, w, include_cheeks=(name == "idle_happy"))[..., None]

        # Match local skin brightness slightly so the blend seam is 100% invisible
        blended_rgb = np.clip(
            base_rgb.astype(np.float32) * (1.0 - mask) + aligned_rgb.astype(np.float32) * mask,
            0,
            255,
        ).astype(np.uint8)
        out_rgba = np.concatenate([blended_rgb, base_a], axis=-1)
        out_img = Image.fromarray(out_rgba, mode="RGBA")
        out_path = ASSETS_DIR / f"{name}.png"
        out_img.save(out_path)
        print(f"  Saved {out_path.name} ({out_img.size})")

        # Save zoomed face crop for QA
        face_crop = out_img.crop((int(w * 0.12), int(h * 0.28), int(w * 0.44), int(h * 0.58)))
        bg = Image.new("RGBA", face_crop.size, (26, 24, 38, 255))
        bg.alpha_composite(face_crop)
        thumbs.append(bg.convert("RGB"))

    if thumbs:
        tw, th = thumbs[0].size
        strip = Image.new("RGB", (tw * len(thumbs), th))
        for i, t in enumerate(thumbs):
            strip.paste(t, (i * tw, 0))
        qa_path = scratch / "qa_face_micro_strip.png"
        strip.save(qa_path)
        print(f"Saved face QA strip: {qa_path}")


if __name__ == "__main__":
    main()
