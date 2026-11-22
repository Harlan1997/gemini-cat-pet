"""Entrypoint for the Gemini Catgirl 2D Desktop Pet."""

import sys

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from pet.config import ASSETS_DIR, load_config
from pet.pet_window import GeminiPetWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    config = load_config()
    pet = GeminiPetWindow(config)

    tray_icon = QSystemTrayIcon(QIcon(str(ASSETS_DIR / "idle.png")), parent=app)
    tray_icon.setToolTip("Gemini 猫猫桌宠")

    tray_menu = QMenu()
    show_act = QAction("显示猫猫", tray_menu)
    show_act.triggered.connect(pet.show_pet)
    tray_menu.addAction(show_act)

    hide_act = QAction("隐藏猫猫", tray_menu)
    hide_act.triggered.connect(pet.hide_pet)
    tray_menu.addAction(hide_act)

    rem_act = QAction("提醒设置...", tray_menu)
    rem_act.triggered.connect(pet.open_reminder_settings)
    tray_menu.addAction(rem_act)

    tray_menu.addSeparator()

    quit_act = QAction("退出", tray_menu)
    quit_act.triggered.connect(app.quit)
    tray_menu.addAction(quit_act)

    tray_icon.setContextMenu(tray_menu)
    tray_icon.activated.connect(
        lambda reason: pet.show_pet()
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick
        else None
    )
    pet.tray_notify_requested.connect(
        lambda title, msg: tray_icon.showMessage(title, msg, QSystemTrayIcon.MessageIcon.Information, 6000)
    )
    tray_icon.show()

    pet.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
