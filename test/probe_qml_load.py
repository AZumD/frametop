#!/usr/bin/env python3
"""Load display-settings/main.qml offscreen and print QML errors."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "display-settings"))
sys.path.insert(0, os.path.join(ROOT, "layout"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuickControls2 import QQuickStyle  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ft_display_settings import Backend  # noqa: E402


def main():
    app = QApplication([])
    QQuickStyle.setStyle("org.kde.desktop")
    eng = QQmlApplicationEngine()

    def on_warnings(warnings):
        for w in warnings:
            print("WARN:", w.toString())

    eng.warnings.connect(on_warnings)
    backend = Backend()
    eng.rootContext().setContextProperty("backend", backend)
    eng.rootContext().setContextProperty("startPage", "instruments")
    qml = os.path.join(ROOT, "display-settings", "main.qml")
    eng.load(QUrl.fromLocalFile(qml))
    n = len(eng.rootObjects())
    print("roots", n)
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
