"""Petit graphique de l'évolution de la vitesse."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class SpeedGraph(QWidget):
    def __init__(self, height=60):
        super().__init__()
        self.samples: list[float] = []
        self.setMinimumHeight(height)

    def set_samples(self, samples):
        self.samples = list(samples)[-120:]
        self.update()

    def paintEvent(self, _):
        if len(self.samples) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height() - 4
        mx = max(self.samples) or 1
        step = w / (len(self.samples) - 1)
        pts = [QPointF(i * step, 2 + h - (v / mx) * h) for i, v in enumerate(self.samples)]
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        fill = QPainterPath(path)
        fill.lineTo(w, h + 2)
        fill.lineTo(0, h + 2)
        fill.closeSubpath()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor(139, 92, 246, 110))
        g.setColorAt(1, QColor(59, 130, 246, 0))
        p.fillPath(fill, g)
        lg = QLinearGradient(0, 0, w, 0)
        lg.setColorAt(0, QColor("#8b5cf6"))
        lg.setColorAt(1, QColor("#3b82f6"))
        p.setPen(QPen(lg, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
