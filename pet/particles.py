"""Programmatic 2D Gemini four-point star and Zzz particle effects."""

from dataclasses import dataclass
import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)


@dataclass
class StarParticle:
    x: float
    y: float
    vx: float
    vy: float
    size: float
    life: float
    max_life: float
    rotation: float
    rot_speed: float
    kind: str = "star"  # "star" or "zzz"


class ParticleSystem:
    """Manages floating Gemini four-point stars and sleepy Zzz symbols."""

    def __init__(self) -> None:
        self.particles: list[StarParticle] = []

    def spawn_stars(self, cx: float, cy: float, count: int = 6, spread: float = 48.0) -> None:
        """Burst glowing four-point stars around (cx, cy)."""
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(18.0, 55.0)
            self.particles.append(
                StarParticle(
                    x=cx + random.uniform(-spread * 0.5, spread * 0.5),
                    y=cy + random.uniform(-spread * 0.4, spread * 0.4),
                    vx=math.cos(angle) * speed * 0.6,
                    vy=-abs(math.sin(angle) * speed) - 24.0,
                    size=random.uniform(7.0, 15.0),
                    life=0.0,
                    max_life=random.uniform(0.8, 1.45),
                    rotation=random.uniform(-20.0, 20.0),
                    rot_speed=random.uniform(-45.0, 45.0),
                    kind="star",
                )
            )

    def spawn_heart(self, cx: float, cy: float) -> None:
        """Spawn a cute floating pink-purple heart when continuously petting her."""
        self.particles.append(
            StarParticle(
                x=cx + random.uniform(-16.0, 16.0),
                y=cy + random.uniform(-8.0, 6.0),
                vx=random.uniform(-14.0, 14.0),
                vy=random.uniform(-44.0, -28.0),
                size=random.uniform(8.5, 13.0),
                life=0.0,
                max_life=random.uniform(1.0, 1.5),
                rotation=random.uniform(-14.0, 14.0),
                rot_speed=random.uniform(-18.0, 18.0),
                kind="heart",
            )
        )

    def spawn_zzz(self, cx: float, cy: float) -> None:
        """Spawn a floating Zzz particle for sleepy mode."""
        self.particles.append(
            StarParticle(
                x=cx + random.uniform(-8.0, 12.0),
                y=cy,
                vx=random.uniform(8.0, 18.0),
                vy=random.uniform(-34.0, -24.0),
                size=random.uniform(12.0, 16.0),
                life=0.0,
                max_life=1.8,
                rotation=random.uniform(-10.0, 10.0),
                rot_speed=random.uniform(-8.0, 8.0),
                kind="zzz",
            )
        )

    def update(self, dt: float) -> None:
        alive: list[StarParticle] = []
        for p in self.particles:
            p.life += dt
            if p.life < p.max_life:
                p.x += p.vx * dt
                p.y += p.vy * dt
                p.rotation += p.rot_speed * dt
                alive.append(p)
        self.particles = alive

    def draw(self, painter: QPainter) -> None:
        if not self.particles:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for p in self.particles:
            progress = p.life / p.max_life
            alpha = int(255 * (1.0 - progress) * min(1.0, progress * 4.5))
            if alpha <= 2:
                continue
            painter.save()
            painter.translate(p.x, p.y)
            painter.rotate(p.rotation)

            if p.kind == "zzz":
                font = QFont("Segoe UI", int(p.size), QFont.Weight.Bold)
                painter.setFont(font)
                painter.setPen(QColor(185, 160, 255, alpha))
                painter.drawText(QPointF(-p.size * 0.4, p.size * 0.4), "Z")
            elif p.kind == "heart":
                s = p.size * (0.75 + 0.25 * math.sin(progress * math.pi))
                path = QPainterPath()
                path.moveTo(0, s * 0.35)
                path.cubicTo(-s * 0.9, -s * 0.35, -s * 0.45, -s * 0.95, 0, -s * 0.35)
                path.cubicTo(s * 0.45, -s * 0.95, s * 0.9, -s * 0.35, 0, s * 0.35)
                path.closeSubpath()

                grad = QLinearGradient(-s, -s, s, s)
                grad.setColorAt(0.0, QColor(255, 150, 210, alpha))
                grad.setColorAt(1.0, QColor(235, 110, 235, alpha))
                painter.setBrush(grad)
                painter.setPen(QPen(QColor(255, 225, 240, alpha), 1.0))
                painter.drawPath(path)
            else:
                s = p.size * (0.7 + 0.3 * math.sin(progress * math.pi))
                inner = s * 0.28
                path = QPainterPath()
                path.moveTo(0, -s)
                path.quadTo(inner * 0.5, -inner * 0.5, s, 0)
                path.quadTo(inner * 0.5, inner * 0.5, 0, s)
                path.quadTo(-inner * 0.5, inner * 0.5, -s, 0)
                path.quadTo(-inner * 0.5, -inner * 0.5, 0, -s)
                path.closeSubpath()

                grad = QLinearGradient(-s, -s, s, s)
                grad.setColorAt(0.0, QColor(120, 210, 255, alpha))
                grad.setColorAt(0.5, QColor(168, 125, 255, alpha))
                grad.setColorAt(1.0, QColor(245, 145, 240, alpha))

                painter.setBrush(grad)
                painter.setPen(QPen(QColor(255, 225, 145, alpha), 1.1))
                painter.drawPath(path)

            painter.restore()
        painter.restore()
