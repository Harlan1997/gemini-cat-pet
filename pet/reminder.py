"""Scheduled reminders (eating, sleeping, studying/break) and settings UI."""

from datetime import date, datetime
from typing import Any

from PySide6.QtCore import QObject, QTime, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from pet.dialogue import REMINDER_MESSAGES


class ReminderManager(QObject):
    """Checks daily meal/sleep schedules and periodic study-break intervals."""

    reminder_triggered = Signal(str, str, str)  # (title, message, expression)

    def __init__(self, reminders_cfg: dict[str, Any], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cfg = reminders_cfg
        self._fired_today: dict[str, date] = {}
        self._study_elapsed_sec = 0

        self._timer = QTimer(self)
        self._timer.setInterval(10_000)  # check every 10 seconds
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def update_config(self, reminders_cfg: dict[str, Any]) -> None:
        self._cfg = reminders_cfg
        self._study_elapsed_sec = 0

    def trigger_now(self, kind: str) -> None:
        title, message, expr = REMINDER_MESSAGES[kind]
        self.reminder_triggered.emit(title, message, expr)

    def _tick(self) -> None:
        now = datetime.now()
        today = now.date()
        hhmm = now.strftime("%H:%M")

        daily_slots = [
            ("lunch", "lunch_enabled", "lunch_time"),
            ("dinner", "dinner_enabled", "dinner_time"),
            ("sleep", "sleep_enabled", "sleep_time"),
        ]
        for kind, en_key, time_key in daily_slots:
            if self._cfg.get(en_key, True) and self._cfg.get(time_key) == hhmm:
                if self._fired_today.get(kind) != today:
                    self._fired_today[kind] = today
                    self.trigger_now(kind)

        if self._cfg.get("study_enabled", True):
            self._study_elapsed_sec += 10
            interval_sec = max(1, int(self._cfg.get("study_interval_minutes", 45))) * 60
            if self._study_elapsed_sec >= interval_sec:
                self._study_elapsed_sec = 0
                self.trigger_now("study")


class ReminderSettingsDialog(QDialog):
    """Dialog to configure lunch, dinner, sleep, and study-break reminders."""

    def __init__(
        self,
        reminders_cfg: dict[str, Any],
        on_test_callback,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gemini 猫猫 - 作息与学习提醒设置")
        self.setMinimumWidth(360)
        self._on_test = on_test_callback

        root = QVBoxLayout(self)

        daily_group = QGroupBox("每日定时提醒")
        daily_form = QFormLayout(daily_group)

        self.lunch_chk = QCheckBox("开启午餐提醒")
        self.lunch_chk.setChecked(bool(reminders_cfg.get("lunch_enabled", True)))
        self.lunch_time = QTimeEdit(self._parse_time(reminders_cfg.get("lunch_time", "12:00")))
        self.lunch_time.setDisplayFormat("HH:mm")
        daily_form.addRow(self.lunch_chk, self.lunch_time)

        self.dinner_chk = QCheckBox("开启晚餐提醒")
        self.dinner_chk.setChecked(bool(reminders_cfg.get("dinner_enabled", True)))
        self.dinner_time = QTimeEdit(self._parse_time(reminders_cfg.get("dinner_time", "18:30")))
        self.dinner_time.setDisplayFormat("HH:mm")
        daily_form.addRow(self.dinner_chk, self.dinner_time)

        self.sleep_chk = QCheckBox("开启睡觉提醒")
        self.sleep_chk.setChecked(bool(reminders_cfg.get("sleep_enabled", True)))
        self.sleep_time = QTimeEdit(self._parse_time(reminders_cfg.get("sleep_time", "23:30")))
        self.sleep_time.setDisplayFormat("HH:mm")
        daily_form.addRow(self.sleep_chk, self.sleep_time)

        root.addWidget(daily_group)

        study_group = QGroupBox("学习 / 专注休息提醒")
        study_layout = QHBoxLayout(study_group)
        self.study_chk = QCheckBox("每隔")
        self.study_chk.setChecked(bool(reminders_cfg.get("study_enabled", True)))
        self.study_spin = QSpinBox()
        self.study_spin.setRange(5, 180)
        self.study_spin.setValue(int(reminders_cfg.get("study_interval_minutes", 45)))
        self.study_spin.setSuffix(" 分钟")
        study_layout.addWidget(self.study_chk)
        study_layout.addWidget(self.study_spin)
        study_layout.addWidget(QLabel("提醒一次喝水/休息"))
        study_layout.addStretch(1)
        root.addWidget(study_group)

        test_row = QHBoxLayout()
        for label, kind in [("测试吃饭", "lunch"), ("测试睡觉", "sleep"), ("测试学习", "study")]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, k=kind: self._on_test(k))
            test_row.addWidget(btn)
        root.addLayout(test_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def _parse_time(value: str) -> QTime:
        t = QTime.fromString(value, "HH:mm")
        return t if t.isValid() else QTime(12, 0)

    def get_config(self) -> dict[str, Any]:
        return {
            "lunch_enabled": self.lunch_chk.isChecked(),
            "lunch_time": self.lunch_time.time().toString("HH:mm"),
            "dinner_enabled": self.dinner_chk.isChecked(),
            "dinner_time": self.dinner_time.time().toString("HH:mm"),
            "sleep_enabled": self.sleep_chk.isChecked(),
            "sleep_time": self.sleep_time.time().toString("HH:mm"),
            "study_enabled": self.study_chk.isChecked(),
            "study_interval_minutes": self.study_spin.value(),
        }
