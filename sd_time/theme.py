"""Dark grey theme with a green accent: Fusion style + palette + stylesheet."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def _ui_asset(name: str) -> str:
    """Absolute, forward-slash path for use in QSS url() (works from a PyInstaller build too)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return (base / "assets" / "ui" / name).as_posix()

C = {
    "bg": "#232323",
    "sidebar": "#191919",
    "card": "#2b2b2b",
    "row": "#2b2b2b",
    "row_hover": "#313131",
    "alt_row": "#2f2f2f",
    "header": "#1e1e1e",
    "border": "#3b3b3b",
    "hover": "#363636",
    "nav_hover": "#222222",
    "input": "#1c1c1c",
    "input_border": "#4a4a4a",   # lighter than "border": fields must stand out on cards
    "text": "#e6e6e6",
    "muted": "#9a9a9a",
    # Olive green. "accent" is for fills (buttons, badges) and is dark enough for white
    # text (4.3:1); "accent_text" is the lighter shade for text and lines on dark grey.
    "accent": "#638521",
    "accent_hover": "#719726",
    "accent_text": "#8db837",
    "on_accent": "#ffffff",
    "today_col": "#292c27",      # today's column in the calendar, faint green tint
    "scroll": "#4a4a4a",
    "danger": "#e5534b",
    "danger_hover": "#ef6c65",
    "grid": "#363636",
}

QSS = f"""
QWidget {{ font-family: "Segoe UI"; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {C['bg']}; }}

#Sidebar {{ background: {C['sidebar']}; border-right: 1px solid {C['header']}; }}
#BrandText {{ color: {C['text']}; font-size: 13pt; font-weight: 700; letter-spacing: 2px; }}
#Brand {{ color: {C['text']}; font-size: 13pt; font-weight: 700; padding: 18px 16px 12px 16px;
          letter-spacing: 2px; }}
QListWidget#Nav {{ background: transparent; border: none; outline: 0; }}
/* One visible left edge (~20px) for the whole sidebar: logo, the drawn part of each
   item icon, section headers and the timer below. Paddings compensate for the empty
   margin inside the icons and the font's side bearing (measured, see tools). */
QListWidget#Nav::item {{ padding: 10px 13px 10px 12px; color: {C['text']};
                         border-left: 3px solid transparent; }}
QListWidget#Nav::item:hover {{ background: {C['nav_hover']}; }}
QListWidget#Nav::item:disabled {{ color: {C['muted']}; background: transparent;
                                  padding: 18px 13px 6px 14px; }}
QListWidget#Nav::item:selected {{ background: {C['hover']}; color: {C['accent_text']};
                                  border-left: 3px solid {C['accent_text']}; }}

#Card {{ background: {C['card']}; border: 1px solid {C['header']}; }}
#CardHeader {{ background: {C['header']}; }}
#EntryRow {{ background: {C['row']}; border-top: 1px solid {C['header']}; }}
#EntryRow:hover {{ background: {C['row_hover']}; }}
#TopBar {{ background: {C['card']}; border: 1px solid {C['header']}; }}

QLabel#Muted {{ color: {C['muted']}; }}
QLabel#Small {{ color: {C['muted']}; font-size: 9pt; }}
QLabel#H1 {{ font-size: 17pt; font-weight: 400; }}
QLabel#Big {{ font-size: 15pt; font-weight: 600; }}
QLabel#Duration {{ font-size: 12pt; font-weight: 600; }}
QLabel#Picker {{ padding: 4px 6px; border-radius: 3px; }}
QLabel#Picker:hover {{ background: {C['hover']}; }}

QLineEdit, QComboBox, QDateEdit, QDateTimeEdit, QTimeEdit, QSpinBox, QDoubleSpinBox,
QKeySequenceEdit, QPlainTextEdit {{
    background: {C['input']}; border: 1px solid {C['input_border']}; border-radius: 3px;
    padding: 5px 8px; color: {C['text']}; selection-background-color: {C['accent']}; }}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QDateTimeEdit:hover, QSpinBox:hover,
QKeySequenceEdit:hover {{ border-color: #5c5c5c; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QDateTimeEdit:focus, QTimeEdit:focus,
QSpinBox:focus {{ border-color: {C['accent_text']}; }}
/* Visible dropdown arrows (the default ones vanish on the dark palette). */
QComboBox, QDateEdit, QDateTimeEdit {{ padding-right: 26px; }}
QComboBox::drop-down, QDateEdit::drop-down, QDateTimeEdit::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right; width: 24px; border: none; }}
QComboBox::down-arrow, QDateEdit::down-arrow, QDateTimeEdit::down-arrow {{
    image: url("{_ui_asset('chevron-down.svg')}"); width: 12px; height: 12px; }}
/* Steppers: a spin box without arrows between "−" and "+" buttons. */
QToolButton#Step {{ background: {C['card']}; border: 1px solid {C['input_border']};
                    border-radius: 3px; color: {C['text']}; font-size: 12pt; font-weight: 600;
                    min-width: 30px; min-height: 30px; padding: 0; }}
QToolButton#Step:hover {{ background: {C['hover']}; color: {C['accent_text']};
                          border-color: {C['accent_text']}; }}
QToolButton#Step:pressed {{ background: {C['accent']}; color: {C['on_accent']}; }}
QToolButton#Step:disabled {{ color: #555555; border-color: {C['border']}; }}
QSpinBox#StepValue {{ min-height: 20px; padding: 5px 4px; }}
/* The stepper's own arrows are hidden this way (see widgets.Stepper for why not NoButtons). */
QSpinBox#StepValue::up-button, QSpinBox#StepValue::down-button {{ width: 0; border: none; }}
QSpinBox#StepValue::up-arrow, QSpinBox#StepValue::down-arrow {{ width: 0; height: 0; }}
QLineEdit#Flat {{ background: transparent; border: 1px solid transparent; }}
QLineEdit#Flat:hover {{ border-color: {C['border']}; }}
QLineEdit#Flat:focus {{ border-color: {C['accent_text']}; background: {C['input']}; }}
QLineEdit#BigInput {{ font-size: 11pt; padding: 8px 10px; }}
QComboBox QAbstractItemView {{ background: {C['card']}; border: 1px solid {C['border']};
                               selection-background-color: {C['hover']}; }}

QPushButton {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 3px;
               padding: 6px 14px; color: {C['text']}; }}
QPushButton:hover {{ background: {C['hover']}; }}
QPushButton:checked {{ background: {C['hover']}; border-color: {C['accent_text']}; }}
QPushButton#Primary {{ background: {C['accent']}; border: none; color: {C['on_accent']}; font-weight: 600;
                       padding: 9px 26px; }}
QPushButton#Primary:hover {{ background: {C['accent_hover']}; }}
QPushButton#Stop {{ background: {C['danger']}; border: none; color: white; font-weight: 600;
                    padding: 9px 26px; }}
QPushButton#Stop:hover {{ background: {C['danger_hover']}; }}
QPushButton#Link {{ background: transparent; border: none; color: {C['accent_text']}; padding: 4px 6px; }}
QPushButton#Link:hover {{ text-decoration: underline; }}
QPushButton#Time {{ background: transparent; border: 1px solid transparent; padding: 4px 8px; }}
QPushButton#Time:hover {{ border-color: {C['border']}; }}
QToolButton#Pomo {{ background: transparent; border: 1px solid {C['input_border']};
                    border-radius: 3px; padding: 0; }}
QToolButton#Pomo:hover {{ background: {C['hover']}; }}
QToolButton#Pomo:checked {{ background: {C['accent']}; border-color: {C['accent']}; }}
QToolButton#Icon {{ background: transparent; border: none; border-radius: 3px; padding: 4px; }}
QToolButton#Icon:hover {{ background: {C['hover']}; }}
QToolButton#Icon::menu-indicator {{ image: none; }}

QTableWidget, QTreeWidget, QListWidget {{
    background: {C['card']}; alternate-background-color: {C['alt_row']}; border: 1px solid {C['header']};
    gridline-color: {C['grid']}; outline: 0; }}
QTableWidget::item, QTreeWidget::item {{ padding: 6px 4px; }}
QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {{
    background: {C['hover']}; color: {C['text']}; }}
QHeaderView::section {{ background: {C['header']}; color: {C['muted']}; border: none;
                        border-bottom: 1px solid {C['border']}; padding: 7px 8px; font-weight: 600; }}
QTableCornerButton::section {{ background: {C['header']}; border: none; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {C['scroll']}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {C['scroll']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: {C['card']}; border: 1px solid {C['border']}; padding: 4px 0; }}
QMenu::item {{ padding: 6px 24px 6px 14px; }}
QMenu::item:selected {{ background: {C['hover']}; }}
QMenu::separator {{ height: 1px; background: {C['border']}; margin: 4px 0; }}

#Popup {{ background: {C['card']}; border: 1px solid {C['border']}; }}
QToolTip {{ background: {C['header']}; color: {C['text']}; border: 1px solid {C['border']}; }}
QCalendarWidget QWidget {{ alternate-background-color: {C['card']}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    role = QPalette.ColorRole
    for r, color in (
        (role.Window, C["bg"]), (role.WindowText, C["text"]), (role.Base, C["input"]),
        (role.AlternateBase, C["card"]), (role.Text, C["text"]), (role.Button, C["card"]),
        (role.ButtonText, C["text"]), (role.Highlight, C["accent"]),
        (role.HighlightedText, C["on_accent"]), (role.ToolTipBase, C["header"]),
        (role.ToolTipText, C["text"]), (role.PlaceholderText, C["muted"]),
        (role.Link, C["accent_text"]), (role.BrightText, "#ffffff"),
    ):
        pal.setColor(r, QColor(color))
    for r in (role.Text, role.WindowText, role.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, r, QColor(C["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
