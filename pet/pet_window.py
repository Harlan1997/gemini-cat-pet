"""Main transparent 2D desktop pet window with real-time Live2D-style micro-animations."""

import math
import random
import time
from typing import Any

from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCursor,
    QMouseEvent,
    QPainter,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from pet.activity_watcher import ActivityReactor, ActivitySnapshot, inspect_current_activity
from pet.bubble import SpeechBubble
from pet.config import ASSETS_DIR, save_config
from pet.dialogue import pick_line
from pet.fullscreen import is_fullscreen_on_widget_monitor
from pet.live_deformer import ProneIdleRig, SoftPoseRig
from pet.particles import ParticleSystem
from pet.reminder import ReminderManager, ReminderSettingsDialog

EXPRESSION_LABELS: dict[str, str] = {
    "idle": "趴桌晃脚 (默认活体待机) 💭",
    "nap": "趴桌瞌睡 🌙",
    "side_sleep": "侧躺安睡 🌠",
    "purr": "摸头呼噜噜 😻",
    "groom": "猫猫爪爪洗脸 🐱",
    "pounce": "盘腿玩星芒 ✦",
    "shy": "害羞鸭子坐 💕",
    "sleepy": "抱尾打盹 💤",
    "stretch": "伸懒腰打哈欠 🌟",
    "drag": "拎猫悬空 🎀",
}

IDLE_FACE_KEYS = ("idle", "idle_half", "idle_closed", "idle_happy", "idle_talk")

SECONDARY_POSE_KEYS = (
    "nap",
    "side_sleep",
    "purr",
    "groom",
    "pounce",
    "shy",
    "sleepy",
    "stretch",
    "drag",
)

# Relative visual height vs standing pose (keeps head size consistent across poses)
POSE_HEIGHT_RATIO: dict[str, float] = {
    "idle": 0.58,
    "nap": 0.46,
    "side_sleep": 0.48,
    "purr": 1.00,
    "groom": 0.70,
    "pounce": 0.70,
    "shy": 0.70,
    "sleepy": 0.73,
    "stretch": 0.78,
    "drag": 0.85,
}


class GeminiPetWindow(QWidget):
    """Frameless transparent HD 2D desktop pet window with silky live micro-animations."""

    tray_notify_requested = Signal(str, str)  # (title, message)

    def __init__(self, config: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self._pet_height: int = int(config.get("pet_height", 300))
        self._always_on_top: bool = bool(config.get("always_on_top", True))
        self._auto_pose: bool = bool(config.get("auto_pose", True))
        self._hide_on_fullscreen: bool = bool(config.get("hide_on_fullscreen", True))
        self._activity_aware: bool = bool(config.get("activity_aware", True))
        self._hidden_by_fullscreen: bool = False
        self._manually_hidden: bool = False

        self._apply_window_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)

        # Raw full-HD PIL images and real-time OpenCV live deformer rigs
        self._raw_images: dict[str, Image.Image] = {}
        self._idle_rig: ProneIdleRig | None = None
        self._pose_rigs: dict[str, SoftPoseRig] = {}
        self._pose_logical_sizes: dict[str, tuple[int, int]] = {}
        self._cached_dpr: float = 0.0
        self._load_raw_images()

        self._expression = "idle"
        self._expr_revert_at = 0.0
        self._state = "idle"  # "idle" or "sleepy"

        # Smooth crossfade state (zero hard-popping cuts!)
        self._last_drawn_key: str = "idle"
        self._last_drawn_pix: QPixmap | None = None
        self._last_drawn_meta: tuple[int, int, int] = (0, 0, 0)  # (w, h, pad_b)
        self._prev_pix: QPixmap | None = None
        self._prev_meta: tuple[int, int, int] = (0, 0, 0)
        self._prev_key: str = "idle"
        self._crossfade_elapsed: float = 1.0
        self._crossfade_duration: float = 0.26

        # Live organic micro-animation states
        now = time.monotonic()
        self._t0 = now
        self._tail_phase = 0.0
        self._feet_phase = 0.0
        self._look_x = 0.0
        self._look_y = 0.0

        # Blinking state machine: open -> half -> closed -> half -> open
        self._blink_phase = "open"
        self._blink_stage_until = 0.0
        self._next_blink_at = now + random.uniform(2.2, 4.5)
        self._double_blink_pending = False

        # Independent ear twitch impulses (0..1)
        self._ear_l_twitch = 0.0
        self._ear_r_twitch = 0.0
        self._ear_l_vel = 0.0
        self._ear_r_vel = 0.0
        self._next_ear_twitch_at = now + random.uniform(3.0, 7.0)

        # Continuous mouse-rub petting bliss (0..1)
        self._pet_bliss = 0.0
        self._last_hover_pos: QPoint | None = None
        self._next_pet_particle_at = 0.0
        self._pet_line_cooldown_until = 0.0

        # Talking lip-sync window
        self._talk_until = 0.0

        # Calm autonomous behavior rhythm (50-95s so she stays cozy instead of PPT-flipping)
        self._next_behavior_at = now + random.uniform(45.0, 80.0)
        self._next_zzz_at = 0.0

        # Drag & pendulum physics state
        self._dragging = False
        self._drag_moved = False
        self._drag_offset = QPoint()
        self._press_pos = QPoint()
        self._last_drag_x = 0
        self._tilt_angle = 0.0
        self._tilt_vel = 0.0
        self._drag_line_shown = False

        # Sub-components
        self._particles = ParticleSystem()
        self._bubble = SpeechBubble()
        self._reminder_mgr = ReminderManager(self.config["reminders"], self)
        self._reminder_mgr.reminder_triggered.connect(self._on_reminder)
        self._activity_reactor = ActivityReactor()

        self._pad = 36
        self._rebuild_rigs()
        self._restore_position()

        # 60 FPS live animation loop
        self._last_tick = time.monotonic()
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._on_frame)
        self._anim_timer.start()

        # Lightweight 500ms fullscreen watcher (hides pet & pauses CPU when gaming/watching videos)
        self._fs_timer = QTimer(self)
        self._fs_timer.setInterval(500)
        self._fs_timer.timeout.connect(self._check_fullscreen)
        self._fs_timer.start()

        # Lightweight 5s foreground-app / music / battery watcher
        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(5000)
        self._activity_timer.timeout.connect(self._poll_activity)
        self._activity_timer.start()

        QTimer.singleShot(550, lambda: self.say(pick_line("greeting"), duration_ms=5000))

    def _apply_window_flags(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self._always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def _load_raw_images(self) -> None:
        self._raw_images.clear()
        for key in (*IDLE_FACE_KEYS, *SECONDARY_POSE_KEYS):
            path = ASSETS_DIR / f"{key}.png"
            if path.exists():
                with Image.open(path) as im:
                    self._raw_images[key] = im.convert("RGBA")

    def _current_dpr(self) -> float:
        screen = self.screen() or QApplication.primaryScreen()
        return max(1.0, float(screen.devicePixelRatio())) if screen else 1.0

    def _rebuild_rigs(self) -> None:
        dpr = self._current_dpr()
        self._cached_dpr = dpr
        self._pose_rigs.clear()
        self._pose_logical_sizes.clear()
        self._prev_pix = None
        self._last_drawn_pix = None

        max_w = int(self._pet_height * 0.85)
        max_h = int(self._pet_height * 1.15)

        # Build dedicated anatomical Live2D-style deformer for lying-down idle
        idle_faces = {k: self._raw_images[k] for k in IDLE_FACE_KEYS if k in self._raw_images}
        if "idle" in idle_faces:
            base_im = idle_faces["idle"]
            lh = max(40, int(round(self._pet_height * POSE_HEIGHT_RATIO["idle"])))
            lw = max(40, int(round(lh * (base_im.width / base_im.height))))
            self._idle_rig = ProneIdleRig(idle_faces, lw, lh, dpr)
            self._pose_logical_sizes["idle"] = (lw, lh)
            max_w = max(max_w, self._idle_rig.logical_w)
            max_h = max(max_h, self._idle_rig.logical_h)

        # Build gentle continuous breathing/sway rigs for all secondary poses
        for key in SECONDARY_POSE_KEYS:
            im = self._raw_images.get(key)
            if im is None:
                continue
            ratio = POSE_HEIGHT_RATIO.get(key, 1.0)
            lh = max(40, int(round(self._pet_height * ratio)))
            lw = max(40, int(round(lh * (im.width / im.height))))
            rig = SoftPoseRig(im, lw, lh, dpr, pose_kind=key)
            self._pose_rigs[key] = rig
            self._pose_logical_sizes[key] = (lw, lh)
            max_w = max(max_w, rig.logical_w)
            max_h = max(max_h, rig.logical_h)

        self.setFixedSize(max_w + self._pad * 2, max_h + self._pad * 2)

    def _restore_position(self) -> None:
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        px = self.config.get("pos_x")
        py = self.config.get("pos_y")
        if isinstance(px, int) and isinstance(py, int):
            x = max(avail.left(), min(px, avail.right() - self.width()))
            y = max(avail.top(), min(py, avail.bottom() - self.height()))
            self.move(x, y)
        else:
            x = avail.right() - self.width() - 32
            y = avail.bottom() - self.height() + self._pad - 4
            self.move(x, y)

    def _save_position(self) -> None:
        self.config["pos_x"] = self.x()
        self.config["pos_y"] = self.y()
        save_config(self.config)

    def _active_pose_key(self) -> str:
        if self._dragging and self._drag_moved and "drag" in self._pose_rigs:
            return "drag"
        if self._expression == "idle" or self._expression in self._pose_rigs:
            return self._expression
        return "idle"

    def set_expression(self, expr: str, duration_sec: float = 0.0) -> None:
        target = expr if (expr == "idle" or expr in self._pose_rigs) else "idle"
        self._expression = target
        self._expr_revert_at = time.monotonic() + duration_sec if duration_sec > 0 else 0.0
        self.update()

    def say(self, text: str, duration_ms: int = 4500, title: str | None = None) -> None:
        if not self.isVisible():
            return
        self._talk_until = time.monotonic() + min(2.2, 0.65 + len(text) * 0.05)
        anchor = self._bubble_anchor_rect()
        self._bubble.show_message(
            text,
            anchor,
            duration_ms=duration_ms,
            title=title,
            always_on_top=self._always_on_top,
        )

    def _bubble_anchor_rect(self) -> QRect:
        key = self._active_pose_key()
        sw, sh = self._pose_logical_sizes.get(key, (int(self._pet_height * 0.7), self._pet_height))
        top_y = self.height() - self._pad - sh
        left_x = (self.width() - sw) // 2
        return QRect(self.x() + left_x, self.y() + top_y, sw, sh)

    def _on_reminder(self, title: str, message: str, expr: str) -> None:
        if self._hidden_by_fullscreen:
            # Don't pop over a fullscreen game/video; send a gentle tray notification only
            self.tray_notify_requested.emit(title, message)
            return
        if not self.isVisible():
            self._manually_hidden = False
            self.show()
        self._state = "sleepy" if expr == "sleepy" else "idle"
        self.set_expression(expr, duration_sec=11.0)
        self._particles.spawn_stars(self.width() / 2, self.height() * 0.42, count=12, spread=70)
        self.say(message, duration_ms=12_000, title=title)
        self.tray_notify_requested.emit(title, message)

    def _check_fullscreen(self) -> None:
        if not self._hide_on_fullscreen:
            if self._hidden_by_fullscreen:
                self._restore_from_fullscreen()
            return
        if self._manually_hidden or self._dragging:
            return

        fs_active = is_fullscreen_on_widget_monitor(int(self.winId()))
        if fs_active and not self._hidden_by_fullscreen:
            self._hidden_by_fullscreen = True
            self._bubble.hide()
            self.hide()
            self._anim_timer.stop()
        elif not fs_active and self._hidden_by_fullscreen:
            self._restore_from_fullscreen()

    def _restore_from_fullscreen(self) -> None:
        self._hidden_by_fullscreen = False
        self._last_tick = time.monotonic()
        if not self._anim_timer.isActive():
            self._anim_timer.start()
        if not self._manually_hidden:
            self.show()

    def _poll_activity(self) -> None:
        if (
            not self._activity_aware
            or not self.isVisible()
            or self._hidden_by_fullscreen
            or self._dragging
            or self._bubble.isVisible()
        ):
            return
        snap = self._activity_reactor.poll()
        if snap is not None:
            self._react_to_activity(snap)

    def _react_to_activity(self, snap: ActivitySnapshot) -> None:
        cat = snap.category or "activity_unknown"
        self._trigger_ear_twitch("left")
        self._trigger_ear_twitch("right")
        self._particles.spawn_stars(self.width() * 0.42, self.height() * 0.45, count=4, spread=32)

        if cat == "low_battery":
            self.say(pick_line("low_battery"), duration_ms=6500, title=f"低电量警告 ({snap.app_name})")
        else:
            self.say(pick_line(cat), duration_ms=4800)

    def inspect_activity_now(self) -> None:
        """Manually scan current foreground app / background music / battery right away."""
        # Wait 120ms after right-click menu closes so foreground focus returns to the user's app
        QTimer.singleShot(120, lambda: self._react_to_activity(inspect_current_activity()))

    def _update_blink(self, now: float) -> None:
        if self._blink_phase == "open":
            if now >= self._next_blink_at:
                self._blink_phase = "closing"
                self._blink_stage_until = now + 0.045
                self._double_blink_pending = random.random() < 0.22
        elif now >= self._blink_stage_until:
            if self._blink_phase == "closing":
                self._blink_phase = "closed"
                self._blink_stage_until = now + 0.085
            elif self._blink_phase == "closed":
                self._blink_phase = "opening"
                self._blink_stage_until = now + 0.045
            else:
                self._blink_phase = "open"
                if self._double_blink_pending:
                    self._double_blink_pending = False
                    self._next_blink_at = now + 0.14
                else:
                    self._next_blink_at = now + random.uniform(2.8, 5.8)

    def _trigger_ear_twitch(self, side: str) -> None:
        if side == "left":
            self._ear_l_vel = 13.5
        else:
            self._ear_r_vel = 13.5

    def _update_cursor_tracking(self, dt: float) -> None:
        key = self._active_pose_key()
        if key != "idle" or self._dragging:
            self._look_x *= max(0.0, 1.0 - dt * 6.0)
            self._look_y *= max(0.0, 1.0 - dt * 6.0)
            return

        sw, sh = self._pose_logical_sizes.get("idle", (240, 174))
        head_gx = self.x() + (self.width() - sw) / 2.0 + sw * 0.27
        head_gy = self.y() + self.height() - self._pad - sh * 0.56
        cur = QCursor.pos()
        dx = cur.x() - head_gx
        dy = cur.y() - head_gy
        dist = math.hypot(dx, dy)

        if dist < 560.0:
            tx = max(-1.0, min(1.0, dx / 220.0))
            ty = max(-1.0, min(1.0, dy / 190.0))
        else:
            tx, ty = 0.0, 0.0

        alpha = min(1.0, dt * 6.5)
        self._look_x += (tx - self._look_x) * alpha
        self._look_y += (ty - self._look_y) * alpha

    def _on_frame(self) -> None:
        now = time.monotonic()
        dt = min(0.05, max(0.001, now - self._last_tick))
        self._last_tick = now

        if abs(self._current_dpr() - self._cached_dpr) > 0.05:
            self._rebuild_rigs()

        # Revert temporary pose smoothly back to alive lying-down idle
        if self._expr_revert_at > 0 and now >= self._expr_revert_at:
            self._expr_revert_at = 0.0
            self._state = "idle"
            self._expression = "idle"

        # Calm autonomous behavior transitions (disabled if user prefers pure lying-down mode)
        if self._auto_pose and not self._dragging and self._pet_bliss < 0.1 and now >= self._next_behavior_at:
            self._choose_next_behavior(now)

        # Advance organic phases (speed up gently when happily being petted!)
        excitement = 1.0 + 0.95 * self._pet_bliss
        self._tail_phase += dt * 1.55 * excitement
        self._feet_phase += dt * 2.15 * (1.0 + 0.45 * self._pet_bliss)

        # Smoothly decay petting bliss when mouse stops stroking
        if self._pet_bliss > 0.0:
            self._pet_bliss = max(0.0, self._pet_bliss - dt * 0.42)

        # Natural 3-stage blinking
        self._update_blink(now)

        # Random subtle cat ear twitches
        if now >= self._next_ear_twitch_at:
            self._next_ear_twitch_at = now + random.uniform(3.5, 8.5)
            self._trigger_ear_twitch(random.choice(["left", "right"]))

        # Spring-damper physics for both cat ears
        for attr_val, attr_vel in (("_ear_l_twitch", "_ear_l_vel"), ("_ear_r_twitch", "_ear_r_vel")):
            val = getattr(self, attr_val)
            vel = getattr(self, attr_vel)
            acc = -170.0 * val - 15.0 * vel
            vel += acc * dt
            val = max(-0.25, min(1.2, val + vel * dt))
            if abs(val) < 0.005 and abs(vel) < 0.01:
                val, vel = 0.0, 0.0
            setattr(self, attr_val, val)
            setattr(self, attr_vel, vel)

        # Smooth mouse-cursor iris & head glance
        self._update_cursor_tracking(dt)

        # Crossfade progress
        if self._crossfade_elapsed < self._crossfade_duration:
            self._crossfade_elapsed = min(self._crossfade_duration, self._crossfade_elapsed + dt)

        # Sleepy / desk-nap / side-sleep Zzz particles
        if (
            self._state == "sleepy" or self._expression in ("sleepy", "nap", "side_sleep")
        ) and now >= self._next_zzz_at:
            self._next_zzz_at = now + 1.15
            if self._expression in ("nap", "side_sleep"):
                self._particles.spawn_zzz(self.width() * 0.34, self.height() * 0.56)
            else:
                self._particles.spawn_zzz(self.width() * 0.56, self.height() * 0.42)

        # Safety release if LeftButton is no longer held (prevents sticky drag on missed Release)
        if self._dragging and not (QApplication.mouseButtons() & Qt.MouseButton.LeftButton):
            self._cancel_drag()

        # Drag pendulum spring physics
        if not self._dragging:
            spring_k = 120.0
            damping = 13.0
            accel = -spring_k * self._tilt_angle - damping * self._tilt_vel
            self._tilt_vel += accel * dt
            self._tilt_angle += self._tilt_vel * dt
            if abs(self._tilt_angle) < 0.05 and abs(self._tilt_vel) < 0.1:
                self._tilt_angle = 0.0
                self._tilt_vel = 0.0

        self._particles.update(dt)
        self.update()

    def _choose_next_behavior(self, now: float) -> None:
        # Calm, cozy rhythm: occasionally nap, side-sleep, wash face, curl up, stretch, or play with a star
        roll = random.random()
        if roll < 0.18:
            self._state = "sleepy"
            self.set_expression("nap", duration_sec=14.0)
            if random.random() < 0.45:
                self.say(pick_line("nap"), duration_ms=4200)
        elif roll < 0.36:
            self._state = "sleepy"
            self.set_expression("side_sleep", duration_sec=15.0)
            if random.random() < 0.45:
                self.say(pick_line("side_sleep"), duration_ms=4200)
        elif roll < 0.52:
            self._state = "idle"
            self.set_expression("groom", duration_sec=7.0)
            if random.random() < 0.45:
                self.say(pick_line("groom"), duration_ms=4000)
        elif roll < 0.66:
            self._state = "sleepy"
            self.set_expression("sleepy", duration_sec=12.0)
            if random.random() < 0.45:
                self.say(pick_line("sleepy"), duration_ms=4200)
        elif roll < 0.78:
            self._state = "idle"
            self.set_expression("stretch", duration_sec=5.2)
            self._particles.spawn_stars(self.width() / 2, self.height() * 0.30, count=5, spread=45)
            if random.random() < 0.5:
                self.say(pick_line("stretch"), duration_ms=4000)
        elif roll < 0.90:
            self._state = "idle"
            self.set_expression("pounce", duration_sec=6.0)
            self._particles.spawn_stars(self.width() * 0.38, self.height() * 0.44, count=5, spread=34)
            if random.random() < 0.45:
                self.say(pick_line("pounce"), duration_ms=4000)
        else:
            # Stay lying down and just share a cute thought!
            self._state = "idle"
            self.set_expression("idle")
            self.say(pick_line(random.choice(["idle", "thinking"])), duration_ms=4200)

        self._next_behavior_at = now + random.uniform(50.0, 90.0)

    def _sync_bubble_position(self) -> None:
        self._bubble.reposition(self._bubble_anchor_rect())

    def _render_live_frame(self, key: str, now: float) -> tuple[QPixmap | None, int, int, int]:
        """Render the current live-deformed pixmap and its (logical_w, logical_h, pad_b)."""
        t = now - self._t0

        if key == "idle" and self._idle_rig is not None:
            # Pick face expression: petting bliss > blink > talking lip-sync > default
            if self._pet_bliss > 0.28:
                face_key = "idle_happy"
                iris_scale = 0.0
            elif self._blink_phase == "closed":
                face_key = "idle_closed"
                iris_scale = 0.0
            elif self._blink_phase in ("closing", "opening"):
                face_key = "idle_half"
                iris_scale = 0.35
            elif now < self._talk_until and int(t * 7.0) % 2 == 0:
                face_key = "idle_talk"
                iris_scale = 1.0
            else:
                face_key = "idle"
                iris_scale = 1.0

            # Organic multi-harmonic continuous waveforms
            tail1 = math.sin(self._tail_phase) * 0.85 + math.sin(self._tail_phase * 0.43 + 1.1) * 0.2
            tail2 = math.cos(self._tail_phase - 0.55) * 0.85

            # Playful lounging foot-rocking with gentle alternating shoe bobs
            feet = math.sin(self._feet_phase) * 0.72 + math.sin(self._feet_phase * 2.0 + 0.4) * 0.18
            foot_l = math.sin(self._feet_phase + 0.8) * 0.75
            foot_r = math.sin(self._feet_phase + 3.6) * 0.75

            # Cat ears: combine random/hover twitch + gentle blissful relaxation when petted
            ear_l = self._ear_l_twitch + self._pet_bliss * 0.48
            ear_r = self._ear_r_twitch + self._pet_bliss * 0.48
            ahoge = math.sin(t * 2.1 - 0.4) * 0.45 + self._pet_bliss * math.sin(t * 7.5) * 0.4
            breath = math.sin(t * 1.75)
            breeze = math.sin(t * 1.35 + 0.7) * 0.75

            pix = self._idle_rig.render(
                face_key=face_key,
                tail1=tail1,
                tail2=tail2,
                feet=feet,
                foot_l=foot_l,
                foot_r=foot_r,
                ear_l=ear_l,
                ear_r=ear_r,
                ahoge=ahoge,
                breath=breath,
                look_x=self._look_x,
                look_y=self._look_y,
                iris_scale=iris_scale,
                breeze=breeze,
            )
            return pix, self._idle_rig.logical_w, self._idle_rig.logical_h, self._idle_rig.logical_pad_b

        rig = self._pose_rigs.get(key)
        if rig is not None:
            pix = rig.render(t)
            return pix, rig.logical_w, rig.logical_h, rig.logical_pad_b

        return None, 0, 0, 0

    def _draw_pose_pixmap(
        self,
        painter: QPainter,
        pix: QPixmap,
        key: str,
        lw: int,
        lh: int,
        pad_b: int,
        opacity: float,
        settle_scale: float = 1.0,
    ) -> None:
        if opacity <= 0.01:
            return
        baseline_y = float(self.height() - self._pad)
        center_x = self.width() / 2.0

        painter.save()
        painter.setOpacity(opacity)
        if key == "drag":
            pivot_y = baseline_y - (lh - pad_b) * 0.78
            painter.translate(center_x, pivot_y)
            painter.rotate(self._tilt_angle)
            painter.scale(settle_scale, settle_scale)
            painter.drawPixmap(int(-lw / 2.0), int(-(lh - pad_b) * 0.22), pix)
        else:
            painter.translate(center_x, baseline_y + pad_b)
            painter.rotate(self._tilt_angle)
            painter.scale(settle_scale, settle_scale)
            painter.drawPixmap(int(-lw / 2.0), int(-lh), pix)
        painter.restore()

    def paintEvent(self, event) -> None:
        now = time.monotonic()
        key = self._active_pose_key()

        # Trigger smooth crossfade whenever active pose changes
        if key != self._last_drawn_key and self._last_drawn_pix is not None:
            self._prev_pix = self._last_drawn_pix
            self._prev_meta = self._last_drawn_meta
            self._prev_key = self._last_drawn_key
            self._crossfade_elapsed = 0.0
            self._crossfade_duration = 0.12 if (key == "drag" or self._prev_key == "drag") else 0.26

        pix, lw, lh, pad_b = self._render_live_frame(key, now)
        if pix is None or pix.isNull():
            return

        self._last_drawn_key = key
        self._last_drawn_pix = pix
        self._last_drawn_meta = (lw, lh, pad_b)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        if self._prev_pix is not None and self._crossfade_elapsed < self._crossfade_duration:
            u = self._crossfade_elapsed / self._crossfade_duration
            # Smooth cubic ease-in-out
            ease = u * u * (3.0 - 2.0 * u)
            # Gentle subtle elastic settle on incoming pose (0.97 -> 1.0)
            in_scale = 0.97 + 0.03 * ease
            pw, ph, ppad_b = self._prev_meta
            self._draw_pose_pixmap(painter, self._prev_pix, self._prev_key, pw, ph, ppad_b, 1.0 - ease)
            self._draw_pose_pixmap(painter, pix, key, lw, lh, pad_b, ease, settle_scale=in_scale)
        else:
            self._prev_pix = None
            self._draw_pose_pixmap(painter, pix, key, lw, lh, pad_b, 1.0)

        self._particles.draw(painter)

    def _cancel_drag(self) -> None:
        """Safely release stuck drag state if mouse release was lost (e.g. focus steal)."""
        if not self._dragging:
            return
        was_moved = self._drag_moved
        self._dragging = False
        self._drag_moved = False
        if was_moved:
            self._save_position()
            self.set_expression("idle")
            self._pet_bliss = 0.0

    def focusOutEvent(self, event) -> None:
        self._cancel_drag()
        super().focusOutEvent(event)

    def hideEvent(self, event) -> None:
        self._cancel_drag()
        super().hideEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_moved = False
            self._drag_line_shown = False
            self._press_pos = event.globalPosition().toPoint()
            self._drag_offset = self._press_pos - self.frameGeometry().topLeft()
            self._last_drag_x = self._press_pos.x()
            self._state = "idle"
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._cancel_drag()
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                self._cancel_drag()
                return
            gpos = event.globalPosition().toPoint()
            if (gpos - self._press_pos).manhattanLength() > 6:
                self._drag_moved = True
            dx = gpos.x() - self._last_drag_x
            self._last_drag_x = gpos.x()

            target_tilt = max(-22.0, min(22.0, dx * 0.95))
            self._tilt_angle = self._tilt_angle * 0.62 + target_tilt * 0.38

            self.move(gpos - self._drag_offset)
            if self._bubble.isVisible():
                self._sync_bubble_position()

            if self._drag_moved and not self._drag_line_shown and abs(dx) > 3:
                self._drag_line_shown = True
                self.say(pick_line("drag"), duration_ms=3000)
            event.accept()
            return

        # Continuous natural head-rubbing petting & ear-twitch response while hovering!
        pos = event.position().toPoint()
        if self._active_pose_key() == "idle":
            sw, sh = self._pose_logical_sizes.get("idle", (240, 174))
            left_x = (self.width() - sw) / 2.0
            top_y = self.height() - self._pad - sh
            rel_x = (pos.x() - left_x) / max(1.0, float(sw))
            rel_y = (pos.y() - top_y) / max(1.0, float(sh))

            if 0.08 <= rel_x <= 0.46 and 0.06 <= rel_y <= 0.56:
                if self._last_hover_pos is not None:
                    move_dist = (pos - self._last_hover_pos).manhattanLength()
                    if 2 <= move_dist <= 45:
                        self._pet_bliss = min(1.0, self._pet_bliss + move_dist * 0.012)
                        # Instant cute ear twitch when brushing over an ear!
                        if rel_y <= 0.28 and self._ear_l_twitch < 0.1 and rel_x < 0.24:
                            self._trigger_ear_twitch("left")
                        elif rel_y <= 0.26 and self._ear_r_twitch < 0.1 and rel_x > 0.30:
                            self._trigger_ear_twitch("right")

                        now = time.monotonic()
                        if self._pet_bliss > 0.35 and now >= self._next_pet_particle_at:
                            self._next_pet_particle_at = now + 0.26
                            self._particles.spawn_heart(pos.x(), pos.y() - 10)
                            if random.random() < 0.45:
                                self._particles.spawn_stars(pos.x(), pos.y(), count=2, spread=28)
                        if self._pet_bliss > 0.72 and now >= self._pet_line_cooldown_until:
                            self._pet_line_cooldown_until = now + 8.0
                            self.say(pick_line("purr"), duration_ms=3600)
            self._last_hover_pos = pos

    def leaveEvent(self, event) -> None:
        self._last_hover_pos = None
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            if self._drag_moved:
                self._save_position()
                self.set_expression("idle")
                self._pet_bliss = 0.0
            else:
                self._handle_click(event.position().toPoint())
            self._next_behavior_at = time.monotonic() + random.uniform(45.0, 85.0)
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_moved = False
            self._state = "idle"
            self.set_expression("purr", duration_sec=4.5)
            self._particles.spawn_heart(self.width() / 2, self.height() * 0.34)
            self._particles.spawn_stars(self.width() / 2, self.height() * 0.38, count=10, spread=65)
            self.say(pick_line("happy"), duration_ms=4000)
            event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        step = 24 if delta > 0 else -24
        self.set_pet_height(self._pet_height + step)
        event.accept()

    def _handle_click(self, pos: QPoint) -> None:
        self._state = "idle"
        key = self._active_pose_key()
        sw, sh = self._pose_logical_sizes.get(key, (240, self._pet_height))
        left_x = (self.width() - sw) / 2.0
        top_y = self.height() - self._pad - sh
        rel_x = (pos.x() - left_x) / max(1.0, float(sw))
        rel_y = (pos.y() - top_y) / max(1.0, float(sh))

        if key == "idle":
            if rel_x <= 0.50 and rel_y <= 0.72:
                # Head pat right in place — melts into happy closed-eye bliss + ear twitch + hearts!
                self._pet_bliss = 1.0
                self._trigger_ear_twitch("left")
                self._trigger_ear_twitch("right")
                self._particles.spawn_heart(pos.x(), pos.y() - 12)
                self._particles.spawn_stars(pos.x(), pos.y(), count=6, spread=38)
                self.say(pick_line("purr"), duration_ms=3800)
                return
            # Poking her tail/feet playfully triggers a cute cat pose!
            expr = random.choice(["pounce", "groom", "shy", "stretch"])
            self.set_expression(expr, duration_sec=5.0)
            self._particles.spawn_stars(pos.x(), pos.y(), count=6, spread=38)
            line_cat = expr if expr in ("pounce", "groom", "stretch") else "poke_body"
            self.say(pick_line(line_cat), duration_ms=4000)
        else:
            if rel_y <= 0.36:
                self.set_expression("purr", duration_sec=4.5)
                self._particles.spawn_heart(pos.x(), pos.y() - 8)
                self._particles.spawn_stars(pos.x(), pos.y(), count=8, spread=42)
                self.say(pick_line("purr"), duration_ms=3800)
            else:
                self.set_expression("idle")
                self._particles.spawn_stars(pos.x(), pos.y(), count=5, spread=32)

    def set_pet_height(self, new_height: int) -> None:
        clamped = max(180, min(520, int(new_height)))
        if clamped == self._pet_height:
            return
        old_bottom = self.y() + self.height()
        old_center_x = self.x() + self.width() // 2

        self._pet_height = clamped
        self.config["pet_height"] = self._pet_height
        save_config(self.config)
        self._rebuild_rigs()

        self.move(old_center_x - self.width() // 2, old_bottom - self.height())
        if self._bubble.isVisible():
            self._sync_bubble_position()
        self.update()

    def set_always_on_top(self, enabled: bool) -> None:
        self._always_on_top = enabled
        self.config["always_on_top"] = enabled
        save_config(self.config)
        self._apply_window_flags()
        self.show()

    def set_auto_pose(self, enabled: bool) -> None:
        self._auto_pose = enabled
        self.config["auto_pose"] = enabled
        save_config(self.config)
        if not enabled:
            self._state = "idle"
            self.set_expression("idle")

    def set_hide_on_fullscreen(self, enabled: bool) -> None:
        self._hide_on_fullscreen = enabled
        self.config["hide_on_fullscreen"] = enabled
        save_config(self.config)
        if not enabled and self._hidden_by_fullscreen:
            self._restore_from_fullscreen()

    def set_activity_aware(self, enabled: bool) -> None:
        self._activity_aware = enabled
        self.config["activity_aware"] = enabled
        save_config(self.config)

    def open_reminder_settings(self) -> None:
        dlg = ReminderSettingsDialog(
            self.config["reminders"],
            on_test_callback=self._reminder_mgr.trigger_now,
            parent=self,
        )
        if dlg.exec():
            new_rem = dlg.get_config()
            self.config["reminders"] = new_rem
            save_config(self.config)
            self._reminder_mgr.update_config(new_rem)
            self._pet_bliss = 1.0
            self.say("提醒设置已更新！我会准时叫你喵~ ✦", duration_ms=3500)

    def _show_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)

        scan_act = QAction("看看我在干嘛 👀", menu)
        scan_act.triggered.connect(self.inspect_activity_now)
        menu.addAction(scan_act)

        expr_menu = menu.addMenu("切换姿势 / 表情")
        expr_group = QActionGroup(expr_menu)
        expr_group.setExclusive(True)
        for key, label in EXPRESSION_LABELS.items():
            act = QAction(label, expr_menu, checkable=True)
            act.setChecked(self._expression == key)
            act.triggered.connect(lambda _=False, k=key: self._manual_expression(k))
            expr_group.addAction(act)
            expr_menu.addAction(act)

        size_menu = menu.addMenu("缩放大小")
        for label, val in [("小 (240px)", 240), ("中 (300px)", 300), ("大 (380px)", 380), ("超大 (460px)", 460)]:
            act = QAction(label, size_menu)
            act.triggered.connect(lambda _=False, v=val: self.set_pet_height(v))
            size_menu.addAction(act)

        auto_act = QAction("空闲时偶尔切换大姿势", menu, checkable=True)
        auto_act.setChecked(self._auto_pose)
        auto_act.triggered.connect(self.set_auto_pose)
        menu.addAction(auto_act)

        fs_act = QAction("全屏时自动隐藏", menu, checkable=True)
        fs_act.setChecked(self._hide_on_fullscreen)
        fs_act.triggered.connect(self.set_hide_on_fullscreen)
        menu.addAction(fs_act)

        act_aware = QAction("应用/进程感知互动", menu, checkable=True)
        act_aware.setChecked(self._activity_aware)
        act_aware.triggered.connect(self.set_activity_aware)
        menu.addAction(act_aware)

        top_act = QAction("窗口置顶", menu, checkable=True)
        top_act.setChecked(self._always_on_top)
        top_act.triggered.connect(self.set_always_on_top)
        menu.addAction(top_act)

        menu.addSeparator()

        rem_act = QAction("吃饭/睡觉/学习提醒设置...", menu)
        rem_act.triggered.connect(self.open_reminder_settings)
        menu.addAction(rem_act)

        test_menu = menu.addMenu("立即触发提醒")
        for label, kind in [("吃饭提醒", "lunch"), ("睡觉提醒", "sleep"), ("学习休息提醒", "study")]:
            act = QAction(label, test_menu)
            act.triggered.connect(lambda _=False, k=kind: self._reminder_mgr.trigger_now(k))
            test_menu.addAction(act)

        menu.addSeparator()

        hide_act = QAction("隐藏到系统托盘", menu)
        hide_act.triggered.connect(self.hide_pet)
        menu.addAction(hide_act)

        quit_act = QAction("退出桌宠", menu)
        quit_act.triggered.connect(QApplication.quit)
        menu.addAction(quit_act)

        menu.exec(global_pos)

    def _manual_expression(self, expr: str) -> None:
        self._state = "sleepy" if expr in ("sleepy", "nap", "side_sleep") else "idle"
        self.set_expression(expr, duration_sec=0.0)
        self._particles.spawn_stars(self.width() / 2, self.height() * 0.42, count=6, spread=42)
        if expr in ("nap", "side_sleep", "purr", "groom", "pounce", "shy", "sleepy", "stretch", "drag"):
            self.say(pick_line(expr), duration_ms=3800)

    def hide_pet(self) -> None:
        self._manually_hidden = True
        self._hidden_by_fullscreen = False
        self._bubble.hide()
        self.hide()
        self._anim_timer.stop()

    def show_pet(self) -> None:
        self._manually_hidden = False
        self._hidden_by_fullscreen = False
        self._last_tick = time.monotonic()
        if not self._anim_timer.isActive():
            self._anim_timer.start()
        self.show()
        self.raise_()
        self._pet_bliss = 0.8
        self.say("从托盘里丝滑钻回来啦喵~ ✦", duration_ms=3000)
