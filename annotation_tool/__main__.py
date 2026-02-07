"""
Module entrypoint for the annotation tool.

Run:
    python3 -m annotation_tool
"""

from __future__ import annotations

import sys

from PyQt5.QtWidgets import QApplication

from .window import AnnotationToolWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("PyQt Annotation Tool")

    window = AnnotationToolWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

