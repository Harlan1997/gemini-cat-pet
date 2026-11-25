"""Real-time 60FPS Live2D-style 2D mesh deformation engine powered by OpenCV remap."""

import math
from typing import Any

import cv2
import numpy as np
from PIL import Image
from PySide6.QtGui import QImage, QPixmap


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / max(1e-6, edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _rot_basis(
    nx: np.ndarray,
    ny: np.ndarray,
    cx: float,
    cy: float,
    weight: np.ndarray,
    max_rad: float,
    w: int,
    h: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Build linearised local rotation displacement basis (inverse-map dx, dy in pixels)."""
    # Compute in isotropic pixel space relative to pivot (cx*w, cy*h)
    rx = (nx - cx) * w
    ry = (ny - cy) * h
    # Small-angle tangent vector for +max_rad clockwise rotation: (dx, dy) = (-ry * rad, +rx * rad)
    # Inverse mapping for cv2.remap subtracts forward displacement
    bx = (ry * max_rad * weight).astype(np.float32)
    by = (-rx * max_rad * weight).astype(np.float32)
    return bx, by


def _dist_to_polyline(
    nx: np.ndarray, ny: np.ndarray, pts: list[tuple[float, float]]
) -> tuple[np.ndarray, np.ndarray]:
    """Return (min_distance, normalized_arc_s) to a 2D polyline."""
    seg_lens = [
        math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        for i in range(len(pts) - 1)
    ]
    total_len = sum(seg_lens)
    cum = 0.0

    best_d2 = np.full(nx.shape, 1e9, dtype=np.float32)
    best_s = np.zeros(nx.shape, dtype=np.float32)

    for i, slen in enumerate(seg_lens):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        vx, vy = x1 - x0, y1 - y0
        v2 = vx * vx + vy * vy + 1e-9
        t = np.clip(((nx - x0) * vx + (ny - y0) * vy) / v2, 0.0, 1.0)
        px = x0 + t * vx
        py = y0 + t * vy
        d2 = (nx - px) ** 2 + (ny - py) ** 2
        s = (cum + t * slen) / total_len
        better = d2 < best_d2
        best_d2 = np.where(better, d2, best_d2)
        best_s = np.where(better, s, best_s)
        cum += slen

    return np.sqrt(best_d2), best_s


class ProneIdleRig:
    """Anatomical Live2D-style continuous mesh deformer for the lying-on-tummy idle pose."""

    # Padding fractions around the base sprite so moving tail/feet/ears never clip
    PAD_L = 0.07
    PAD_R = 0.09
    PAD_T = 0.12
    PAD_B = 0.04

    def __init__(
        self,
        face_images: dict[str, Image.Image],
        target_logical_w: int,
        target_logical_h: int,
        dpr: float,
    ) -> None:
        self.dpr = dpr
        self.base_logical_w = target_logical_w
        self.base_logical_h = target_logical_h

        phys_base_w = max(1, int(round(target_logical_w * dpr)))
        phys_base_h = max(1, int(round(target_logical_h * dpr)))

        self.pad_l = int(round(phys_base_w * self.PAD_L))
        self.pad_r = int(round(phys_base_w * self.PAD_R))
        self.pad_t = int(round(phys_base_h * self.PAD_T))
        self.pad_b = int(round(phys_base_h * self.PAD_B))

        self.phys_w = phys_base_w + self.pad_l + self.pad_r
        self.phys_h = phys_base_h + self.pad_t + self.pad_b
        self.logical_w = int(round(self.phys_w / dpr))
        self.logical_h = int(round(self.phys_h / dpr))
        self.logical_pad_b = int(round(self.pad_b / dpr))

        # Prepare padded HiDPI Lanczos RGBA arrays for every face expression
        self.faces: dict[str, np.ndarray] = {}
        for key, pil_im in face_images.items():
            resized = pil_im.resize((phys_base_w, phys_base_h), Image.Resampling.LANCZOS)
            arr = np.asarray(resized, dtype=np.uint8)
            padded = np.zeros((self.phys_h, self.phys_w, 4), dtype=np.uint8)
            padded[
                self.pad_t : self.pad_t + phys_base_h,
                self.pad_l : self.pad_l + phys_base_w,
            ] = arr
            self.faces[key] = padded

        self._build_basis_fields(phys_base_w, phys_base_h)

    def _build_basis_fields(self, bw: int, bh: int) -> None:
        yy, xx = np.mgrid[0 : self.phys_h, 0 : self.phys_w].astype(np.float32)
        self.base_x = xx
        self.base_y = yy

        # Normalized coordinates in the unpadded original sprite [0..1]
        nx = (xx - self.pad_l) / float(bw)
        ny = (yy - self.pad_t) / float(bh)

        # 1. Fluffy cat tail traveling S-wave (root (0.665, 0.515) -> tip (0.605, 0.075))
        tail_pts = [
            (0.665, 0.515),
            (0.680, 0.425),
            (0.625, 0.355),
            (0.540, 0.295),
            (0.510, 0.205),
            (0.535, 0.115),
            (0.605, 0.075),
        ]
        t_dist, t_s = _dist_to_polyline(nx, ny, tail_pts)
        # Keep strictly inside the tail's open corridor so hair/legs stay untouched
        tail_box = (
            _smoothstep(0.43, 0.47, nx)
            * (1.0 - _smoothstep(0.71, 0.745, nx))
            * (1.0 - _smoothstep(0.49, 0.54, ny))
        )
        w_tail = (1.0 - _smoothstep(0.085, 0.135, t_dist)) * tail_box * _smoothstep(0.05, 0.22, t_s)
        self.tail1_x, self.tail1_y = _rot_basis(
            nx, ny, 0.665, 0.515, w_tail * (t_s ** 1.15), math.radians(8.5), bw, bh
        )
        # Secondary traveling wave (horizontal/perpendicular ripple along mid-to-tip tail)
        wave_env = w_tail * np.sin(math.pi * np.clip(t_s, 0.0, 1.0)) * (t_s ** 0.5)
        self.tail2_x = (-wave_env * (bw * 0.016)).astype(np.float32)
        self.tail2_y = (-wave_env * (bh * 0.008)).astype(np.float32)

        # 2. Playful kicking feet / lower legs (knee anchor ~(0.885, 0.585))
        # Stay strictly right of x=0.635 and above y=0.61 so thigh/skirt & tail are never distorted,
        # while maintaining weight=1.0 generously past both shoe silhouettes (zero foldover!).
        w_legs = (
            _smoothstep(0.62, 0.67, nx)
            * (1.0 - _smoothstep(0.47, 0.61, ny))
        )
        self.feet_x, self.feet_y = _rot_basis(
            nx, ny, 0.885, 0.585, w_legs, math.radians(6.2), bw, bh
        )
        # Gentle differential ankle sway using wide smooth left/right split (guarantees positive Jacobian!)
        split_l = (1.0 - _smoothstep(0.81, 0.90, nx)) * w_legs * (1.0 - _smoothstep(0.32, 0.46, ny))
        self.foot_l_x, self.foot_l_y = _rot_basis(
            nx, ny, 0.835, 0.42, split_l, math.radians(3.2), bw, bh
        )

        split_r = _smoothstep(0.84, 0.92, nx) * w_legs * (1.0 - _smoothstep(0.35, 0.48, ny))
        self.foot_r_x, self.foot_r_y = _rot_basis(
            nx, ny, 0.885, 0.44, split_r, math.radians(3.5), bw, bh
        )

        # 3. Independent cat ear twitches + bouncy top ahoge
        d_ear_l = np.hypot((nx - 0.150) / 0.080, (ny - 0.180) / 0.105)
        w_ear_l = (
            (1.0 - _smoothstep(0.55, 1.15, d_ear_l))
            * (1.0 - _smoothstep(0.23, 0.28, ny))
            * (1.0 - _smoothstep(0.22, 0.26, nx))
        )
        self.ear_l_x, self.ear_l_y = _rot_basis(
            nx, ny, 0.195, 0.245, w_ear_l, math.radians(-17.5), bw, bh
        )

        d_ear_r = np.hypot((nx - 0.375) / 0.080, (ny - 0.150) / 0.105)
        w_ear_r = (
            (1.0 - _smoothstep(0.55, 1.15, d_ear_r))
            * (1.0 - _smoothstep(0.20, 0.25, ny))
            * _smoothstep(0.315, 0.345, nx)
        )
        self.ear_r_x, self.ear_r_y = _rot_basis(
            nx, ny, 0.340, 0.225, w_ear_r, math.radians(17.5), bw, bh
        )

        d_ahoge = np.hypot((nx - 0.270) / 0.065, (ny - 0.125) / 0.070)
        w_ahoge = (1.0 - _smoothstep(0.4, 1.05, d_ahoge)) * (1.0 - _smoothstep(0.165, 0.195, ny))
        self.ahoge_x, self.ahoge_y = _rot_basis(
            nx, ny, 0.250, 0.185, w_ahoge, math.radians(11.0), bw, bh
        )

        # 4. Gentle breathing (upper torso & head softly rise/fall; elbows & floor stay anchored!)
        w_breath = (
            (1.0 - _smoothstep(0.76, 0.90, ny))
            * (1.0 - _smoothstep(0.52, 0.72, nx))
        )
        self.breath_y = (w_breath * (bh * 0.0055)).astype(np.float32)

        # 5. Subtle mouse-following head lean (head/ears/upper hair only, anchored at chin/hands)
        d_head = np.hypot((nx - 0.275) / 0.22, (ny - 0.32) / 0.25)
        w_head = (1.0 - _smoothstep(0.55, 1.10, d_head)) * (1.0 - _smoothstep(0.52, 0.65, ny))
        self.head_x = (-w_head * (bw * 0.0055)).astype(np.float32)
        self.head_y = (-w_head * (bh * 0.0045)).astype(np.float32)

        # 6. Live iris eye-tracking strictly inside the two small pupil zones!
        d_iris_l = np.hypot((nx - 0.214) / 0.023, (ny - 0.448) / 0.032)
        d_iris_r = np.hypot((nx - 0.305) / 0.024, (ny - 0.441) / 0.032)
        w_iris = np.maximum(
            1.0 - _smoothstep(0.45, 1.0, d_iris_l),
            1.0 - _smoothstep(0.45, 1.0, d_iris_r),
        )
        self.iris_x = (-w_iris * (bw * 0.0036)).astype(np.float32)
        self.iris_y = (-w_iris * (bh * 0.0028)).astype(np.float32)

        # 7. Flowing hair-tip & right ribbon breeze
        w_hair_l = (1.0 - _smoothstep(0.14, 0.23, nx)) * _smoothstep(0.44, 0.60, ny) * (1.0 - _smoothstep(0.84, 0.92, ny))
        w_ribbon_r = _smoothstep(0.76, 0.86, nx) * _smoothstep(0.74, 0.82, ny)
        w_breeze = np.clip(w_hair_l + w_ribbon_r, 0.0, 1.0)
        self.breeze_x = (-w_breeze * (bw * 0.006)).astype(np.float32)
        self.breeze_y = (-w_breeze * (bh * 0.004)).astype(np.float32)

    def render(
        self,
        face_key: str,
        tail1: float,
        tail2: float,
        feet: float,
        foot_l: float,
        foot_r: float,
        ear_l: float,
        ear_r: float,
        ahoge: float,
        breath: float,
        look_x: float,
        look_y: float,
        iris_scale: float,
        breeze: float,
    ) -> QPixmap:
        """Evaluate real-time continuous warp and return a crisp HiDPI QPixmap."""
        src = self.faces.get(face_key)
        if src is None:
            src = self.faces["idle"]

        map_x = (
            self.base_x
            + tail1 * self.tail1_x
            + tail2 * self.tail2_x
            + feet * self.feet_x
            + foot_l * self.foot_l_x
            + foot_r * self.foot_r_x
            + ear_l * self.ear_l_x
            + ear_r * self.ear_r_x
            + ahoge * self.ahoge_x
            + look_x * self.head_x
            + (look_x * iris_scale) * self.iris_x
            + breeze * self.breeze_x
        )
        map_y = (
            self.base_y
            + tail1 * self.tail1_y
            + tail2 * self.tail2_y
            + feet * self.feet_y
            + foot_l * self.foot_l_y
            + foot_r * self.foot_r_y
            + ear_l * self.ear_l_y
            + ear_r * self.ear_r_y
            + ahoge * self.ahoge_y
            + breath * self.breath_y
            + look_y * self.head_y
            + (look_y * iris_scale) * self.iris_y
            + breeze * self.breeze_y
        )

        warped = cv2.remap(
            src,
            map_x,
            map_y,
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )
        qimg = QImage(
            warped.data,
            self.phys_w,
            self.phys_h,
            self.phys_w * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()
        pix = QPixmap.fromImage(qimg)
        pix.setDevicePixelRatio(self.dpr)
        return pix


class SoftPoseRig:
    """Gentle continuous breathing & hair/body-sway mesh deformer for secondary poses."""

    PAD_X = 0.06
    PAD_Y = 0.06

    def __init__(
        self,
        pil_im: Image.Image,
        target_logical_w: int,
        target_logical_h: int,
        dpr: float,
        pose_kind: str,
    ) -> None:
        self.dpr = dpr
        self.pose_kind = pose_kind
        phys_bw = max(1, int(round(target_logical_w * dpr)))
        phys_bh = max(1, int(round(target_logical_h * dpr)))
        self.pad_x = int(round(phys_bw * self.PAD_X))
        self.pad_y = int(round(phys_bh * self.PAD_Y))
        self.phys_w = phys_bw + self.pad_x * 2
        self.phys_h = phys_bh + self.pad_y * 2
        self.logical_w = int(round(self.phys_w / dpr))
        self.logical_h = int(round(self.phys_h / dpr))
        self.logical_pad_b = int(round(self.pad_y / dpr))

        resized = pil_im.resize((phys_bw, phys_bh), Image.Resampling.LANCZOS)
        padded = np.zeros((self.phys_h, self.phys_w, 4), dtype=np.uint8)
        padded[self.pad_y : self.pad_y + phys_bh, self.pad_x : self.pad_x + phys_bw] = np.asarray(
            resized, dtype=np.uint8
        )
        self.src = padded

        yy, xx = np.mgrid[0 : self.phys_h, 0 : self.phys_w].astype(np.float32)
        self.base_x = xx
        self.base_y = yy
        nx = (xx - self.pad_x) / float(phys_bw)
        ny = (yy - self.pad_y) / float(phys_bh)

        # Floor-anchored smooth upper sway & breathing field (feet stay 100% locked!)
        anchor = 1.0 - _smoothstep(0.68, 0.94, ny)
        self.sway_x = (-anchor * (1.0 - ny) * (phys_bw * 0.014)).astype(np.float32)
        self.breath_y = (anchor * (phys_bh * 0.008)).astype(np.float32)

        # Gentle hair/tail outer-edge wave (peaks on left/right edges away from torso center)
        edge_w = np.clip(np.abs(nx - 0.5) * 2.2 - 0.35, 0.0, 1.0) * (1.0 - _smoothstep(0.75, 0.95, ny))
        self.wave_x = (-edge_w * np.sin(ny * math.pi * 2.0) * (phys_bw * 0.011)).astype(np.float32)
        self.wave_y = (-edge_w * (phys_bh * 0.006)).astype(np.float32)

    def render(self, t: float) -> QPixmap:
        if self.pose_kind == "groom":
            sway = math.sin(t * 4.4) * 0.75
            breath = math.sin(t * 4.4 + 0.6) * 0.55
            wave = math.sin(t * 2.8) * 0.8
        elif self.pose_kind in ("sleepy", "nap", "side_sleep"):
            sway = math.sin(t * 1.0) * 0.22
            breath = math.sin(t * 1.35) * 1.15
            wave = math.sin(t * 1.1 + 1.0) * 0.42
        elif self.pose_kind == "pounce":
            sway = math.sin(t * 2.4) * 0.55
            breath = math.sin(t * 2.2) * 0.65
            wave = math.sin(t * 2.8) * 0.85
        elif self.pose_kind == "purr":
            sway = math.sin(t * 3.8) * 0.75
            breath = math.sin(t * 3.8) * 0.55
            wave = math.sin(t * 5.5) * 1.2
        elif self.pose_kind == "stretch":
            sway = math.sin(t * 1.8) * 0.35
            breath = (0.5 + 0.5 * math.sin(t * 2.2)) * 1.4
            wave = math.sin(t * 2.4) * 0.7
        elif self.pose_kind == "drag":
            sway = math.sin(t * 6.5) * 0.6
            breath = math.sin(t * 5.0) * 0.45
            wave = math.sin(t * 7.0) * 1.1
        else:
            sway = math.sin(t * 2.0) * 0.5
            breath = math.sin(t * 2.4) * 0.7
            wave = math.sin(t * 2.6) * 0.8

        map_x = self.base_x + sway * self.sway_x + wave * self.wave_x
        map_y = self.base_y + breath * self.breath_y + wave * self.wave_y

        warped = cv2.remap(
            self.src,
            map_x,
            map_y,
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )
        qimg = QImage(
            warped.data,
            self.phys_w,
            self.phys_h,
            self.phys_w * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()
        pix = QPixmap.fromImage(qimg)
        pix.setDevicePixelRatio(self.dpr)
        return pix
