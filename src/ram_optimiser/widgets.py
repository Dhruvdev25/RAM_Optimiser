"""Reusable custom-painted dashboard widgets."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from .core import format_bytes


def panel(parent=None, padding=18):
    card = QFrame(parent)
    card.setObjectName("panel")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(padding, padding, padding, padding)
    layout.setSpacing(10)
    return card, layout


class LogoMark(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(42, 42)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#102941"))
        painter.setPen(QPen(QColor("#275b82"), 1))
        painter.drawRoundedRect(QRectF(1, 1, 40, 40), 12, 12)
        path = QPainterPath(QPointF(8, 26))
        path.cubicTo(12, 26, 12, 14, 18, 14)
        path.cubicTo(23, 14, 22, 29, 28, 29)
        path.cubicTo(32, 29, 32, 19, 35, 19)
        painter.setPen(QPen(QColor("#5ac6ff"), 2.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)


class GaugeWidget(QWidget):
    """Crisp, vector semicircle gauge with a real percentage or unavailable state."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value: float | None = None
        self.center_text = ""
        self.sub_text = ""
        self.accent = QColor("#48b9ff")
        self.setMinimumHeight(112)
        self.setMaximumHeight(160)

    def set_value(self, value: float | None, center_text: str | None = None,
                  sub_text: str = "Utilization", accent: str | None = None):
        self.value = None if value is None else max(0.0, min(100.0, float(value)))
        self.center_text = center_text if center_text is not None else (f"{self.value:.0f}%" if self.value is not None else "—")
        self.sub_text = sub_text
        if accent:
            self.accent = QColor(accent)
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        radius = min(width * 0.39, height * 0.72)
        cx, cy = width / 2, height * 0.82
        track_pen = QPen(QColor("#1c2834"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        active_pen = QPen(self.accent, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        start_angle = math.pi
        segments = 52
        active_segments = round(segments * (self.value or 0) / 100)
        for index in range(segments):
            a0 = start_angle - math.pi * index / segments
            a1 = start_angle - math.pi * (index + 0.66) / segments
            p0 = QPointF(cx + math.cos(a0) * radius, cy - math.sin(a0) * radius)
            p1 = QPointF(cx + math.cos(a1) * radius, cy - math.sin(a1) * radius)
            painter.setPen(active_pen if self.value is not None and index < active_segments else track_pen)
            painter.drawLine(p0, p1)
        painter.setPen(QColor("#f3f7fb"))
        number_font = QFont("Segoe UI", max(16, min(24, int(width / 18))), QFont.Weight.DemiBold)
        painter.setFont(number_font)
        painter.drawText(QRectF(0, cy - 42, width, 32), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, self.center_text)
        painter.setPen(QColor("#7d8b9a"))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(QRectF(0, cy - 11, width, 18), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, self.sub_text)


class SparklineWidget(QWidget):
    def __init__(self, parent=None, color="#48b9ff"):
        super().__init__(parent)
        self.values: list[float] = []
        self.color = QColor(color)
        self.setMinimumHeight(48)

    def set_values(self, values):
        self.values = [max(0.0, min(100.0, float(value))) for value in values if value is not None]
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 4, -2, -5)
        for fraction in (0.25, 0.5, 0.75):
            y = rect.bottom() - fraction * rect.height()
            painter.setPen(QPen(QColor("#24303c"), 1))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        if len(self.values) < 2:
            painter.setPen(QColor("#728093"))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Collecting real measurements…")
            return
        points = [QPointF(rect.left() + i * rect.width() / (len(self.values) - 1),
                          rect.bottom() - value / 100 * rect.height()) for i, value in enumerate(self.values)]
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.setPen(QPen(self.color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)


class HistoryChart(QWidget):
    """Compact chart that renders collected data only, never sample placeholders."""
    def __init__(self, parent=None, color="#48b9ff", unit="%"):
        super().__init__(parent)
        self.values: list[float | None] = []
        self.timestamps: list[str | None] = []
        self.color = QColor(color)
        self.unit = unit
        self._plot_rect = QRectF()
        self.setMouseTracking(True)
        self.setMinimumHeight(190)

    def set_values(self, values, timestamps=None):
        values = [None if value is None else float(value) for value in values]
        times = list(timestamps or [None] * len(values))
        if len(times) < len(values):
            times = [None] * (len(values) - len(times)) + times
        if len(values) > 1200:
            stride = math.ceil(len(values) / 1200)
            indices = list(range(0, len(values), stride))
            if indices[-1] != len(values) - 1:
                indices.append(len(values) - 1)
            values = [values[i] for i in indices]
            times = [times[i] for i in indices]
        self.values = values
        self.timestamps = times
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(38, 14, -12, -25)
        self._plot_rect = rect
        if not any(v is not None for v in self.values):
            painter.setPen(QColor("#8592a1"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No recorded measurements yet")
            return
        for pct in (0, 25, 50, 75, 100):
            y = rect.bottom() - pct * rect.height() / 100
            painter.setPen(QPen(QColor("#202b37"), 1))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(QColor("#7c8998"))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(QRectF(0, y - 8, 31, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{pct}{self.unit}")
        vals = self.values
        points = []
        for index, value in enumerate(vals):
            if value is None:
                points.append(None)
                continue
            x = rect.left() + index * rect.width() / max(1, len(vals) - 1)
            y = rect.bottom() - max(0, min(100, value)) * rect.height() / 100
            points.append(QPointF(x, y))
        painter.setPen(QPen(self.color, 2.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        path = QPainterPath()
        started = False
        for point in points:
            if point is None:
                started = False
            elif not started:
                path.moveTo(point)
                started = True
            else:
                path.lineTo(point)
        painter.drawPath(path)
        painter.setPen(QColor("#7c8998"))
        painter.drawText(QRectF(rect.left(), rect.bottom() + 5, rect.width(), 16), Qt.AlignmentFlag.AlignLeft, "Oldest")
        painter.drawText(QRectF(rect.left(), rect.bottom() + 5, rect.width(), 16), Qt.AlignmentFlag.AlignRight, "Now")

    def mouseMoveEvent(self, event):
        if len(self.values) < 2 or self._plot_rect.width() <= 0 or not self._plot_rect.contains(event.position()):
            self.setToolTip("")
            return
        position = max(0.0, min(1.0, (event.position().x() - self._plot_rect.left()) / self._plot_rect.width()))
        index = round(position * (len(self.values) - 1))
        value = self.values[index]
        timestamp = self.timestamps[index] if index < len(self.timestamps) else None
        if value is None:
            self.setToolTip("No measurement at this point")
            return
        stamp = timestamp or "Timestamp unavailable"
        self.setToolTip(f"{stamp}\n{value:.1f}{self.unit}")


class MetricTile(QFrame):
    def __init__(self, title: str, value: str = "—", parent=None):
        super().__init__(parent)
        self.setObjectName("metricTile")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        self.title = QLabel(title)
        self.title.setObjectName("eyebrow")
        self.value = QLabel(value)
        self.value.setObjectName("metricValue")
        self.value.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.value)

    def set_value(self, value: str):
        self.value.setText(value)


def make_gauge_card(title: str, glyph: str, color: str):
    card, layout = panel(padding=15)
    card.setMinimumHeight(214)
    header = QWidget()
    row = QVBoxLayout(header)
    row.setContentsMargins(0, 0, 0, 0)
    label = QLabel(f"{glyph}   {title}")
    label.setObjectName("cardTitle")
    row.addWidget(label)
    gauge = GaugeWidget()
    gauge.accent = QColor(color)
    layout.addWidget(header)
    layout.addWidget(gauge, 1)
    return card, gauge


def add_section_title(layout, title: str, caption: str | None = None):
    label = QLabel(title)
    label.setObjectName("sectionTitle")
    layout.addWidget(label)
    if caption:
        sub = QLabel(caption)
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        layout.addWidget(sub)

