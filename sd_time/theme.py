"""SD Time look: dark ground, flat cards, olive-green accent.

Fusion style + palette + one stylesheet. Segoe UI for everything (its digits are tabular).

Design rules kept by the stylesheet:
- every control (button, input, combo, segmented group, header pill) is CTRL_H tall;
- radii: cards 8, controls 5, things inside a control 3;
- controls share one fill (card) and one outline (control_border); hover lightens the fill.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication


def _ui_asset(name: str) -> str:
    """Absolute, forward-slash path for use in QSS url() (works from a PyInstaller build too)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return (base / "assets" / "ui" / name).as_posix()


C = {
    "bg": "#161616",
    "sidebar": "#101010",
    "card": "#1f1f1f",
    "card_border": "#2a2a2a",
    "raised": "#262626",         # chips, round buttons, pills on cards
    "row": "#1f1f1f",
    "row_hover": "#242424",
    "alt_row": "#222222",
    "header": "#1a1a1a",
    "border": "#2c2c2c",
    "control_border": "#353535",  # buttons, segmented group, nav arrows
    "hover": "#2a2a2a",
    "nav_hover": "#1b1b1b",
    "input": "#181818",
    "input_border": "#3d3d3d",
    "text": "#e6e6e6",
    "muted": "#9a9a9a",
    "faint": "#6f6f6f",
    # Olive green. "accent" is for fills (buttons, badges) and is dark enough for white
    # text (4.3:1); "accent_text" is the lighter shade for text and lines on dark grey.
    "accent": "#638521",
    "accent_hover": "#719726",
    "accent_text": "#8db837",
    "accent_soft": "#24301a",    # selected rail item, tinted pills
    "accent_soft_text": "#a9d15a",
    "on_accent": "#ffffff",
    "today_col": "#1f251a",      # today's row/column, faint green tint
    "scroll": "#3d3d3d",
    "danger": "#e5534b",
    "danger_hover": "#ef6c65",
    "grid": "#262626",
}


def _first_font(*names: str) -> str:
    families = set(QFontDatabase.families())
    return next((n for n in names if n in families), names[-1])


CTRL_H = 36                  # height of every control, px
FONT_UI = "Segoe UI"
FONT_MONO = FONT_UI          # numbers use Segoe UI: its digits are tabular


def mono(size_pt: float, bold: bool = False) -> QFont:
    f = QFont(FONT_MONO)
    f.setPointSizeF(size_pt)
    f.setBold(bold)
    return f


def _qss() -> str:
    return f"""
QWidget {{ font-family: "{FONT_UI}"; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {C['bg']}; }}

/* Icon rail */
#Sidebar {{ background: {C['sidebar']}; border-right: 1px solid #1d1d1d; }}
QListWidget#Rail {{ background: transparent; border: none; outline: 0; }}
QListWidget#Rail::item {{ margin: 3px 13px; padding-left: 9px; border-radius: 6px; color: transparent; }}
QListWidget#Rail::item:hover {{ background: #1c1c1c; }}
QListWidget#Rail::item:selected {{ background: {C['accent_soft']}; }}
QLabel#RailTimer {{ color: {C['accent_soft_text']}; font-family: "{FONT_MONO}"; font-size: 9pt; }}

/* Cards and rows */
#Card {{ background: {C['card']}; border: 1px solid {C['card_border']}; border-radius: 8px; }}
#CardFlat {{ background: {C['card']}; border: 1px solid {C['card_border']}; border-radius: 6px; }}
#Banner {{ background: #1e2418; border: 1px solid #34431f; border-radius: 8px; }}
#EntryLine {{ background: transparent; border-bottom: 1px solid {C['card_border']}; }}
#EntryLine:hover {{ background: {C['row_hover']}; }}
#DayGroup {{ background: transparent; }}

QLabel#Muted {{ color: {C['muted']}; }}
QLabel#Faint {{ color: {C['faint']}; }}
QLabel#Small {{ color: {C['muted']}; font-size: 9pt; }}
QLabel#H1 {{ font-size: 19pt; font-weight: 600; }}
QLabel#H2 {{ font-size: 14pt; font-weight: 600; }}
QLabel#H3 {{ font-size: 10.5pt; font-weight: 600; }}
QLabel#Big {{ font-size: 14pt; font-weight: 600; }}
QLabel#Mono {{ font-family: "{FONT_MONO}"; }}
QLabel#MonoMuted {{ font-family: "{FONT_MONO}"; color: {C['muted']}; }}
QLabel#MonoBig {{ font-family: "{FONT_MONO}"; font-size: 20pt; font-weight: 600; }}
QLabel#Pill {{ background: {C['raised']}; border-radius: 5px; padding: 4px 11px;
               font-family: "{FONT_MONO}"; font-size: 9.5pt; }}
QLabel#HeaderPill {{ background: {C['raised']}; border-radius: 5px; padding: 0 14px; color: {C['text']}; }}
QLabel#PillAccent {{ background: {C['accent_soft']}; color: {C['accent_soft_text']};
                     border-radius: 5px; padding: 4px 11px; font-size: 9.5pt; }}
QLabel#Picker {{ border-radius: 5px; padding: 4px 11px; }}

/* Inputs */
QLineEdit, QComboBox, QDateEdit, QDateTimeEdit, QTimeEdit, QSpinBox, QDoubleSpinBox,
QKeySequenceEdit, QPlainTextEdit {{
    background: {C['input']}; border: 1px solid {C['input_border']}; border-radius: 5px;
    padding: 6px 10px; min-height: 22px; color: {C['text']};
    selection-background-color: {C['accent']}; }}
QPlainTextEdit {{ min-height: 0; }}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QDateTimeEdit:hover, QSpinBox:hover,
QKeySequenceEdit:hover {{ border-color: #545454; }}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QDateTimeEdit:focus, QTimeEdit:focus,
QSpinBox:focus {{ border-color: {C['accent_text']}; }}
QComboBox, QDateEdit, QDateTimeEdit {{ padding-right: 28px; }}
QComboBox::drop-down, QDateEdit::drop-down, QDateTimeEdit::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right; width: 26px; border: none; }}
QComboBox::down-arrow, QDateEdit::down-arrow, QDateTimeEdit::down-arrow {{
    image: url("{_ui_asset('chevron-down.svg')}"); width: 12px; height: 12px; }}
QComboBox:disabled {{ color: {C['faint']}; background: transparent; }}
QComboBox::down-arrow:disabled {{ image: none; }}
QComboBox QAbstractItemView {{ background: {C['card']}; border: 1px solid {C['border']};
                               selection-background-color: {C['hover']}; }}
QLineEdit#Flat {{ background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 4px 6px;
                  min-height: 0; }}
QLineEdit#Flat:hover {{ border-color: {C['border']}; }}
QLineEdit#Flat:focus {{ border-color: {C['accent_text']}; background: {C['input']}; }}
QLineEdit#NowInput {{ background: transparent; border: 1px solid transparent; border-radius: 5px;
                      font-size: 13pt; font-weight: 600; padding: 4px 8px; min-height: 0; }}
QLineEdit#NowInput:hover {{ border-color: {C['border']}; }}
QLineEdit#NowInput:focus {{ border-color: {C['accent_text']}; background: {C['input']}; }}

/* Steppers: a spin box without arrows between "−" and "+" buttons. */
QToolButton#Step {{ background: {C['raised']}; border: 1px solid {C['input_border']};
                    border-radius: 5px; color: {C['text']}; font-size: 12pt; font-weight: 600;
                    min-width: 34px; min-height: 34px; padding: 0; }}
QToolButton#Step:hover {{ color: {C['accent_text']}; border-color: {C['accent_text']}; }}
QToolButton#Step:pressed {{ background: {C['accent']}; color: {C['on_accent']}; }}
QToolButton#Step:disabled {{ color: #555555; border-color: {C['border']}; }}
QSpinBox#StepValue {{ min-height: 20px; padding: 6px 4px; }}
/* The stepper's own arrows are hidden this way (see widgets.Stepper for why not NoButtons). */
QSpinBox#StepValue::up-button, QSpinBox#StepValue::down-button {{ width: 0; border: none; }}
QSpinBox#StepValue::up-arrow, QSpinBox#StepValue::down-arrow {{ width: 0; height: 0; }}

/* Buttons */
QPushButton {{ background: {C['card']}; border: 1px solid {C['control_border']}; border-radius: 5px;
               padding: 8px 15px; min-height: 18px; color: {C['text']}; }}
QPushButton:hover {{ background: {C['hover']}; }}
QPushButton:checked {{ background: {C['hover']}; border-color: {C['accent_text']}; }}
QPushButton#Primary {{ background: {C['accent']}; border: 1px solid {C['accent']}; color: {C['on_accent']};
                       font-weight: 600; padding: 8px 20px; }}
QPushButton#Primary:hover {{ background: {C['accent_hover']}; border-color: {C['accent_hover']}; }}
QPushButton#Stop {{ background: {C['danger']}; border: 1px solid {C['danger']}; color: white;
                    font-weight: 600; padding: 8px 20px; }}
QPushButton#Stop:hover {{ background: {C['danger_hover']}; border-color: {C['danger_hover']}; }}
QPushButton#Danger {{ background: transparent; border: 1px solid transparent; color: {C['danger']};
                      padding: 8px 14px; }}
QPushButton#Danger:hover {{ border-color: {C['danger']}; color: {C['danger_hover']}; }}
QPushButton#Link {{ background: transparent; border: none; color: {C['accent_text']}; padding: 4px 6px;
                    min-height: 0; }}
QPushButton#Link:hover {{ text-decoration: underline; }}
QPushButton#Time {{ background: transparent; border: 1px solid transparent; padding: 4px 8px; min-height: 0;
                    font-family: "{FONT_MONO}"; color: {C['muted']}; }}
QPushButton#Time:hover {{ border-color: {C['border']}; color: {C['text']}; }}
QPushButton#GroupHead {{ background: transparent; border: none; border-radius: 5px; text-align: left;
                         padding: 10px 8px; min-height: 0; color: {C['text']}; }}
QPushButton#GroupHead:hover {{ background: {C['row_hover']}; }}
QPushButton#Chip {{ background: {C['raised']}; border: 1px solid #323232; border-radius: 5px;
                    padding: 7px 12px; min-height: 0; text-align: left; }}
QPushButton#Chip:hover {{ border-color: {C['accent_text']}; }}
QPushButton#Currency, QPushButton#CurrencyDefault {{ background: {C['raised']}; border: 1px solid #323232;
                    border-radius: 5px; padding: 6px 12px; min-height: 0; font-weight: 600; }}
QPushButton#Currency:hover, QPushButton#CurrencyDefault:hover {{ border-color: {C['accent_text']}; }}
QPushButton#CurrencyDefault {{ background: {C['accent_soft']}; border-color: #3f5226; color: {C['accent_text']}; }}
QPushButton#MenuButton {{ padding-right: 32px; }}
QPushButton::menu-indicator {{ image: url("{_ui_asset('chevron-down.svg')}"); width: 12px; height: 12px;
    subcontrol-origin: padding; subcontrol-position: center right; right: 12px; }}
/* Segmented control */
QPushButton#Seg {{ background: transparent; border: none; border-radius: 3px; padding: 0 14px;
                   min-height: 0; color: #a8a8a8; font-weight: 600; }}
QPushButton#Seg:hover {{ color: {C['text']}; }}
QPushButton#Seg:checked {{ background: {C['accent_soft']}; color: {C['accent_soft_text']}; }}
#SegGroup {{ background: {C['card']}; border: 1px solid {C['control_border']}; border-radius: 5px; }}
/* Mini timer window */
#MiniCard {{ background: {C['card']}; border: 1px solid #3a3a3a; border-radius: 8px; }}
QLineEdit#MiniInput {{ background: transparent; border: 1px solid transparent; border-radius: 4px;
                       padding: 3px 6px; min-height: 0; font-size: 10.5pt; font-weight: 600; }}
QLineEdit#MiniInput:hover {{ border-color: {C['border']}; }}
QLineEdit#MiniInput:focus {{ border-color: {C['accent_text']}; background: {C['input']}; }}
QLabel#MiniTime {{ font-family: "{FONT_MONO}"; font-size: 15pt; font-weight: 600; padding: 0 4px; }}
QToolButton#MiniStart {{ background: {C['accent']}; border: none; border-radius: 5px; }}
QToolButton#MiniStart:hover {{ background: {C['accent_hover']}; }}
QToolButton#MiniStop {{ background: {C['danger']}; border: none; border-radius: 5px; }}
QToolButton#MiniStop:hover {{ background: {C['danger_hover']}; }}
/* Round timer buttons */
QToolButton#RoundStart {{ background: {C['accent']}; border: none; border-radius: 10px; }}
QToolButton#RoundStart:hover {{ background: {C['accent_hover']}; }}
QToolButton#RoundStop {{ background: {C['danger']}; border: none; border-radius: 10px; }}
QToolButton#RoundStop:hover {{ background: {C['danger_hover']}; }}
QToolButton#RoundSmall {{ background: {C['raised']}; border: 1px solid #333333; border-radius: 8px; }}
QToolButton#RoundSmall:hover {{ border-color: {C['accent_text']}; }}
QToolButton#RoundSmall:disabled {{ background: #1c1c1c; border-color: #262626; }}
QToolButton#Nav {{ background: {C['card']}; border: 1px solid {C['control_border']}; border-radius: 5px; }}
QToolButton#Nav:hover {{ background: {C['hover']}; }}
QToolButton#Nav:checked {{ background: {C['accent_soft']}; border-color: #3f5226; }}
QToolButton#Nav:disabled {{ background: #1a1a1a; border-color: #262626; }}
QToolButton#CardIcon {{ background: transparent; border: none; border-radius: 5px; }}
QToolButton#CardIcon:hover {{ background: {C['raised']}; }}
QToolButton#CardIcon:checked {{ background: {C['accent_soft']}; }}
QToolButton#PomoChip {{ background: {C['raised']}; border: none; border-radius: 5px; padding: 5px 12px 5px 8px;
                        color: #bdbdbd; font-weight: 600; }}
QToolButton#PomoChip:hover {{ color: {C['text']}; }}
QToolButton#PomoChip {{ padding-right: 26px; }}
QToolButton#PomoChip::menu-indicator {{ image: url("{_ui_asset('chevron-down.svg')}"); width: 10px;
    height: 10px; subcontrol-origin: padding; subcontrol-position: center right; right: 9px; }}
QToolButton#PomoChip:checked {{ background: #2b1e1d; color: #f2a59f; }}
QToolButton#PomoChip[kind="potato"]:checked {{ background: #2c2619; color: #e3c48f; }}
QToolButton#PomoChip[kind="cucumber"]:checked {{ background: #1d2a19; color: #addb92; }}
QToolButton#Icon {{ background: transparent; border: none; border-radius: 4px; padding: 4px; }}
QToolButton#Icon:hover {{ background: {C['hover']}; }}
QToolButton#Icon::menu-indicator {{ image: none; }}

/* Tables and lists */
QTableWidget, QTreeWidget, QListWidget {{
    background: {C['card']}; alternate-background-color: {C['alt_row']}; border: 1px solid {C['card_border']};
    border-radius: 6px; gridline-color: {C['grid']}; outline: 0; }}
QTableWidget::item, QTreeWidget::item {{ padding: 6px 4px; }}
QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {{
    background: {C['hover']}; color: {C['text']}; }}
QTreeWidget#ProjectTree::item {{ height: 36px; padding: 0 6px; border: none; }}
QTreeWidget#ProjectTree::item:hover {{ background: {C['row_hover']}; }}
QTreeView::branch {{ background: transparent; }}
QTreeView::branch:hover {{ background: {C['row_hover']}; }}
QTreeView::branch:has-children:closed {{ image: url("{_ui_asset('branch-closed.svg')}"); }}
QTreeView::branch:has-children:open {{ image: url("{_ui_asset('branch-open.svg')}"); }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {C['muted']}; border: none;
                        border-bottom: 1px solid {C['card_border']}; padding: 9px 8px; font-weight: 500; }}
QTableCornerButton::section {{ background: transparent; border: none; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {C['scroll']}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {C['scroll']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 5px; padding: 6px 0; }}
QMenu::item {{ padding: 7px 24px 7px 14px; }}
QMenu::item:selected {{ background: {C['hover']}; }}
QMenu::item:checked {{ color: {C['accent_soft_text']}; font-weight: 600; }}
QMenu::separator {{ height: 1px; background: {C['border']}; margin: 4px 0; }}

#Popup {{ background: {C['card']}; border: 1px solid {C['border']}; border-radius: 6px; }}
QToolTip {{ background: {C['header']}; color: {C['text']}; border: 1px solid {C['border']}; }}
QCalendarWidget QWidget {{ alternate-background-color: {C['card']}; }}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 3px;
    background: {C['input']}; border: 1px solid #555555; }}
QCheckBox::indicator:hover {{ border-color: {C['accent_text']}; }}
QCheckBox::indicator:checked {{ background: {C['accent']}; border-color: {C['accent']};
    image: url("{_ui_asset('check.svg')}"); }}
QCheckBox::indicator:checked:hover {{ background: {C['accent_hover']}; border-color: {C['accent_hover']}; }}
QCheckBox:disabled {{ color: {C['faint']}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont(FONT_UI, 10))
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
    app.setStyleSheet(_qss())
