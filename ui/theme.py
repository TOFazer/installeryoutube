"""Identité visuelle : anthracite, violet, bleu — thèmes sombre et clair."""
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

from services.paths import resource

VIOLET = "#8b5cf6"
BLUE = "#3b82f6"

PALETTES = {
    "dark": dict(bg="#16171d", side="#1c1d24", card="#22232c", card2="#2a2b36", border="#30313d",
                 text="#ececf1", muted="#9a9bab", input="#1a1b22", hover="#2f3040"),
    "light": dict(bg="#f4f5f9", side="#ffffff", card="#ffffff", card2="#eef0f6", border="#dfe1ea",
                  text="#1c1d24", muted="#6b6d7d", input="#f7f8fb", hover="#eceef6"),
}


def colors(theme: str) -> dict:
    return {**PALETTES.get(theme, PALETTES["dark"]), "violet": VIOLET, "blue": BLUE}


def icon(name: str, color: str = "#ececf1", size: int = 20) -> QIcon:
    svg = resource("assets", "icons", f"{name}.svg").read_text(encoding="utf-8").replace("#COLOR", color)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    return QIcon(pm)


def logo_pixmap(size=40) -> QPixmap:
    renderer = QSvgRenderer(str(resource("assets", "logo", "logo.svg")))
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p)
    p.end()
    return pm


def stylesheet(theme: str) -> str:
    c = colors(theme)
    return f"""
* {{ font-family: "Segoe UI Variable", "Segoe UI", "Inter", sans-serif; font-size: 14px; color: {c['text']}; }}
QMainWindow, #central {{ background: {c['bg']}; }}
#sidebar {{ background: {c['side']}; border-right: 1px solid {c['border']}; }}
#brand {{ font-size: 20px; font-weight: 800; }}
#navBtn {{ text-align: left; padding: 11px 14px; border: none; border-radius: 12px; background: transparent; color: {c['muted']}; font-weight: 600; }}
#navBtn:hover {{ background: {c['hover']}; color: {c['text']}; }}
#navBtn:checked {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(139,92,246,0.25), stop:1 rgba(59,130,246,0.15)); color: {c['text']}; }}
#badge {{ background: {VIOLET}; color: white; border-radius: 9px; padding: 1px 7px; font-size: 11px; font-weight: 700; }}
#pageTitle {{ font-size: 26px; font-weight: 800; }}
#heroTitle {{ font-size: 40px; font-weight: 900; color: {VIOLET}; }}
#slogan {{ font-size: 15px; color: {c['muted']}; }}
#muted, QLabel[muted="true"] {{ color: {c['muted']}; }}
#small {{ color: {c['muted']}; font-size: 12px; }}
#card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 18px; }}
#feature {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 16px; }}
#featureTitle {{ font-weight: 700; }}
#chip {{ background: {c['card2']}; border-radius: 8px; padding: 4px 10px; color: {c['text']}; font-size: 12px; }}
#thumb {{ background: {c['card2']}; border-radius: 12px; }}
#videoTitle {{ font-size: 17px; font-weight: 700; }}
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
  padding-left: 12px;
  background: {c['input']}; border: 1px solid {c['border']}; border-radius: 12px; padding: 9px 12px;
  selection-background-color: {VIOLET}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {VIOLET}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{ background: {c['card']}; border: 1px solid {c['border']}; selection-background-color: {VIOLET}; outline: none; padding: 4px; }}
QPushButton {{ background: {c['card2']}; border: 1px solid {c['border']}; border-radius: 12px; padding: 9px 16px; font-weight: 600; }}
QPushButton:hover {{ background: {c['hover']}; border-color: {VIOLET}; }}
QPushButton:disabled {{ color: {c['muted']}; }}
QPushButton#primary {{ border: none; color: white; padding: 12px 22px;
  background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {VIOLET}, stop:1 {BLUE}); }}
QPushButton#primary:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #7c4dee, stop:1 #2f74e8); }}
QPushButton#primary:disabled {{ background: {c['card2']}; color: {c['muted']}; }}
QPushButton#ghost {{ background: transparent; border: none; padding: 6px; border-radius: 9px; }}
QPushButton#ghost:hover {{ background: {c['hover']}; }}
QProgressBar {{ background: {c['card2']}; border: none; border-radius: 4px; max-height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ border-radius: 4px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {VIOLET}, stop:1 {BLUE}); }}
QProgressBar[state="done"]::chunk {{ background: #22c55e; }}
QProgressBar[state="failed"]::chunk {{ background: #ef4444; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QTableWidget {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 14px; gridline-color: transparent;
  selection-background-color: rgba(139,92,246,0.25); selection-color: {c['text']}; alternate-background-color: {c['card2']}; }}
QHeaderView::section {{ background: {c['card']}; color: {c['muted']}; border: none; border-bottom: 1px solid {c['border']}; padding: 8px; font-weight: 600; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {c['border']}; background: {c['input']}; }}
QCheckBox::indicator:checked {{ background: {VIOLET}; border-color: {VIOLET}; }}
QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 6px; }}
QListWidget {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 14px; padding: 6px; }}
QListWidget::item {{ padding: 10px; border-radius: 10px; }}
QListWidget::item:selected {{ background: rgba(139,92,246,0.25); color: {c['text']}; }}
#toast {{ background: {c['card']}; border: 1px solid {VIOLET}; border-radius: 12px; padding: 10px 16px; }}
"""
