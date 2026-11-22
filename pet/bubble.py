"""Floating Gemini-themed speech bubble widget for the desktop pet."""

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


class SpeechBubble(QWidget):
    """Frameless, rounded glassmorphic speech bubble that tracks the pet."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._is_reminder = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(4)

        self._title_label = QLabel()
        self._title_label.setFont(QFont("Microsoft YaHei UI", 9, QFont.Weight.Bold))
        self._title_label.setStyleSheet("color: #FFD98E; background: transparent;")
        self._title_label.hide()

        self._text_label = QLabel()
        self._text_label.setWordWrap(True)
        self._text_label.setMaximumWidth(250)
        self._text_label.setFont(QFont("Microsoft YaHei UI", 9))
        self._text_label.setStyleSheet("color: #F4EEFF; background: transparent;")

        layout.addWidget(self._title_label)
        layout.addWidget(self._text_label)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_message(
        self,
        text: str,
        anchor_rect: QRect,
        duration_ms: int = 4500,
        title: str | None = None,
        always_on_top: bool = True,
    ) -> None:
        """Display the bubble anchored above (or below) the pet's global rect."""
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, always_on_top)
        self._is_reminder = bool(title)

        if title:
            self._title_label.setText(f"✦ {title}")
            self._title_label.show()
        else:
            self._title_label.hide()

        self._text_label.setText(text)
        self.adjustSize()
        self.reposition(anchor_rect)
        self.show()
        self.raise_()
        self._hide_timer.start(duration_ms)

    def reposition(self, anchor_rect: QRect) -> None:
        """Keep the bubble centered above the pet without leaving the screen."""
        screen = QApplication.screenAt(anchor_rect.center()) or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        w, h = self.width(), self.height()
        x = anchor_rect.center().x() - w // 2
        y = anchor_rect.top() - h - 6

        if y < avail.top() + 8:
            y = anchor_rect.bottom() + 6
        x = max(avail.left() + 8, min(x, avail.right() - w - 8))
        y = max(avail.top() + 8, min(y, avail.bottom() - h - 8))
        self.move(QPoint(x, y))

    def mousePressEvent(self, event) -> None:
        self._hide_timer.stop()
        self.hide()
        event.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)

        bg_color = QColor(34, 24, 62, 232) if self._is_reminder else QColor(28, 22, 50, 222)
        painter.fillPath(path, bg_color)

        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if self._is_reminder:
            grad.setColorAt(0.0, QColor(255, 215, 130, 230))
            grad.setColorAt(0.5, QColor(186, 130, 255, 230))
            grad.setColorAt(1.0, QColor(115, 205, 255, 230))
        else:
            grad.setColorAt(0.0, QColor(125, 200, 255, 200))
            grad.setColorAt(0.5, QColor(168, 125, 255, 200))
            grad.setColorAt(1.0, QColor(245, 145, 240, 200))

        painter.setPen(QPen(grad, 1.8))
        painter.drawPath(path)
