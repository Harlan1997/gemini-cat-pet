"""High-precision chroma-key green-screen matting and sprite-sheet slicer."""

from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage


def matte_green_screen(
    img: Image.Image,
    t_low: float = 0.09,
    t_high: float = 0.34,
    min_component_px: int = 80,
) -> Image.Image:
    """Remove solid #00FF00 chroma-key background with edge decontamination & spill removal."""
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    r = rgb[:, :, 0]
    g = rgb[:, :, 1]
    b = rgb[:, :, 2]

    max_rb = np.maximum(r, b)
    green_excess = g - max_rb

    # Soft alpha from green dominance
    alpha = 1.0 - np.clip((green_excess - t_low) / (t_high - t_low), 0.0, 1.0)

    # Ensure definitely pure-green regions are completely transparent
    pure_bg = (green_excess > t_high) | ((g > 0.55) & (r < 0.35) & (b < 0.35) & (green_excess > 0.22))
    alpha[pure_bg] = 0.0

    # Slight morphological cleanup to remove tiny isolated green-screen JPEG specks
    solid_mask = alpha > 0.15
    labeled, num_features = ndimage.label(solid_mask)
    if num_features > 1:
        sizes = ndimage.sum(solid_mask, labeled, range(1, num_features + 1))
        keep = np.zeros(num_features + 1, dtype=bool)
        for i, sz in enumerate(sizes, start=1):
            if sz >= min_component_px:
                keep[i] = True
        alpha[~keep[labeled]] = 0.0

    # Un-premultiply green background (0, 1, 0) from semi-transparent anti-aliased edges
    edge = (alpha > 0.01) & (alpha < 0.99)
    safe_a = np.where(edge, np.maximum(alpha, 0.12), 1.0)

    r_out = np.where(edge, np.clip(r / safe_a, 0.0, 1.0), r)
    b_out = np.where(edge, np.clip(b / safe_a, 0.0, 1.0), b)
    g_out = np.where(edge, np.clip((g - (1.0 - alpha)) / safe_a, 0.0, 1.0), g)

    # Global green-spill suppression (safe because Gemini catgirl palette has no saturated green)
    # Near edges, suppress stronger; interior, gently cap green dominance
    near_transparent = ndimage.binary_dilation(alpha < 0.85, iterations=3)
    max_rb_out = np.maximum(r_out, b_out)
    avg_rb_out = 0.5 * (r_out + b_out)

    spill = g_out > max_rb_out
    g_suppressed_edge = np.minimum(g_out, 0.65 * max_rb_out + 0.35 * avg_rb_out)
    g_suppressed_inner = np.minimum(g_out, max_rb_out + 0.02)
    g_out = np.where(spill & near_transparent, g_suppressed_edge, np.where(spill, g_suppressed_inner, g_out))

    # Zero out RGB on fully transparent pixels to keep clean PNG compression & Qt sampling
    zero_mask = alpha < 0.03
    alpha[zero_mask] = 0.0
    r_out[zero_mask] = 0.0
    g_out[zero_mask] = 0.0
    b_out[zero_mask] = 0.0

    rgba = np.stack(
        [
            np.clip(r_out * 255.0, 0, 255).astype(np.uint8),
            np.clip(g_out * 255.0, 0, 255).astype(np.uint8),
            np.clip(b_out * 255.0, 0, 255).astype(np.uint8),
            np.clip(alpha * 255.0, 0, 255).astype(np.uint8),
        ],
        axis=-1,
    )
    return Image.fromarray(rgba, mode="RGBA")


def crop_tight(img: Image.Image, pad: int = 12) -> Image.Image:
    """Crop RGBA image tightly around non-transparent pixels with padding."""
    bbox = img.getbbox()
    if not bbox:
        return img
    w, h = img.size
    x0 = max(0, bbox[0] - pad)
    y0 = max(0, bbox[1] - pad)
    x1 = min(w, bbox[2] + pad)
    y1 = min(h, bbox[3] + pad)
    return img.crop((x0, y0, x1, y1))


def slice_walk_sheet(
    sheet_rgba: Image.Image,
    expected_frames: int = 4,
) -> list[Image.Image]:
    """Slice a horizontal 1xN sprite sheet into N bottom-aligned frames."""
    arr = np.asarray(sheet_rgba)
    alpha = arr[:, :, 3]
    h, w = alpha.shape

    # Column occupancy (number of opaque pixels per column)
    col_density = (alpha > 40).sum(axis=0)

    # Find contiguous non-empty horizontal spans
    in_span = col_density > max(3, int(h * 0.005))
    spans: list[tuple[int, int]] = []
    start = None
    for x, active in enumerate(in_span):
        if active and start is None:
            start = x
        elif not active and start is not None:
            if x - start > w * 0.06:
                spans.append((start, x))
            start = None
    if start is not None and w - start > w * 0.06:
        spans.append((start, w))

    # If we didn't get exactly expected_frames clean gaps, fall back to lowest-density valleys
    if len(spans) != expected_frames:
        cuts = [0]
        for i in range(1, expected_frames):
            approx = int(w * i / expected_frames)
            win_l = max(1, approx - int(w * 0.08))
            win_r = min(w - 1, approx + int(w * 0.08))
            best_x = win_l + int(np.argmin(col_density[win_l:win_r]))
            cuts.append(best_x)
        cuts.append(w)
        spans = [(cuts[i], cuts[i + 1]) for i in range(expected_frames)]

    raw_frames: list[Image.Image] = []
    for x0, x1 in spans:
        sub = sheet_rgba.crop((x0, 0, x1, h))
        raw_frames.append(crop_tight(sub, pad=10))

    # Normalize all walk frames onto a unified canvas, anchored by bottom-center (feet!)
    max_w = max(f.width for f in raw_frames)
    max_h = max(f.height for f in raw_frames)
    aligned: list[Image.Image] = []
    for f in raw_frames:
        canvas = Image.new("RGBA", (max_w, max_h), (0, 0, 0, 0))
        paste_x = (max_w - f.width) // 2
        paste_y = max_h - f.height
        canvas.paste(f, (paste_x, paste_y), f)
        aligned.append(canvas)

    return aligned


def save_debug_on_dark(rgba: Image.Image, out_path: Path) -> None:
    """Composite RGBA onto dark slate background for quick visual inspection."""
    bg = Image.new("RGBA", rgba.size, (26, 24, 38, 255))
    bg.alpha_composite(rgba)
    bg.convert("RGB").save(out_path)
