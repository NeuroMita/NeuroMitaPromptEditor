# File: ui/node_graph/graph_primitives.py
from __future__ import annotations
from typing import List, Optional, Callable, Dict

from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainterPath, QPen, QPainterPathStroker
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
    QMenu,
    QColorDialog,
)

# Базовые цвета
NODE_BG = QColor("#202020")
NODE_BORDER = QColor("#999999")
NODE_SELECTED = QColor("#FFA500")
TEXT_FG = QColor("#FFFFFF")
TEXT_SECONDARY = QColor("#999999")
EXEC_EDGE = QColor("#FFFFFF")
BRANCH_EDGE = QColor("#FFA500")

# Высота шапки ноды (компактная)
HEADER_H = 24

# Стили шапки по типу ноды: тип -> (emoji, dark_color, light_color)
NODE_TYPE_STYLES: dict = {
    "SET":             ("🔵", "#2a1a4a", "#4a2a8a"),
    "LOG":             ("📋", "#2a2a2a", "#4a4a4a"),
    "ADD_SYSTEM_INFO": ("📎", "#1f3a5a", "#2a5a8a"),
    "RETURN":          ("✅", "#1a4a2a", "#2a7a4a"),
    "IF":              ("⚡", "#4a3a1a", "#8a6a2a"),
    "SEED_MEMORY":     ("🧠", "#4a1a3a", "#7a2a5a"),
}

# Подсветка (hover/selection IF-веток)
PORT_EXEC_COLOR = QColor("#F0F0F0")
PORT_HOVER = QColor("#FFA500")

# Цвета для подчёркивания фактического пути исполнения
PATH_EDGE = QColor("#00C853")        # зелёный для рёбер
PATH_NODE_BORDER = QColor("#00C853") # зелёная рамка у нод
PATH_PORT = QColor("#00C853")        # зелёный для портов

# Превью-панель (кармашек)
PREV_BG = QColor(32, 32, 32, 220)
PREV_BR = QColor("#3a3a3a")
PREV_TEXT = QColor("#E0E0E0")


class PortItem(QGraphicsEllipseItem):
    R = 5

    def __init__(self, owner: "NodeItem", key: str, is_input: bool):
        super().__init__(-PortItem.R, -PortItem.R, 2 * PortItem.R, 2 * PortItem.R, owner)
        self.owner = owner
        self.key = key
        self.is_input = is_input
        self.edges: List["EdgeItem"] = []
        self.is_highlighted = False    # подсветка (оранжевая) для выбора ветки IF / hover UI
        self.path_highlighted = False  # зелёная подсветка фактического маршрута
        self.setBrush(QBrush(PORT_EXEC_COLOR))
        self.setPen(QPen(Qt.NoPen))
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

    def add_edge(self, e: "EdgeItem"):
        if e not in self.edges:
            self.edges.append(e)

    def remove_edge(self, e: "EdgeItem"):
        if e in self.edges:
            self.edges.remove(e)

    def center_in_scene(self) -> QPointF:
        return self.mapToScene(self.rect().center())

    def _apply_visual(self):
        # Приоритет: путь (зелёный) > обычная подсветка (оранжевая) > дефолт
        if self.path_highlighted:
            self.setBrush(QBrush(PATH_PORT))
            self.setPen(QPen(PATH_PORT, 1.6))
        elif self.is_highlighted:
            self.setBrush(QBrush(PORT_HOVER))
            self.setPen(QPen(PORT_HOVER, 1.5))
        else:
            self.setBrush(QBrush(PORT_EXEC_COLOR))
            self.setPen(QPen(Qt.NoPen))

    def set_highlighted(self, on: bool):
        self.is_highlighted = on
        self._apply_visual()

    def set_path_highlight(self, on: bool):
        self.path_highlighted = on
        self._apply_visual()

    def hoverEnterEvent(self, event):
        if not (self.is_highlighted or self.path_highlighted):
            self.setBrush(QBrush(PORT_HOVER))
        return super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not (self.is_highlighted or self.path_highlighted):
            self.setBrush(QBrush(PORT_EXEC_COLOR))
        return super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for e in list(self.edges):
                e.update_path()
        return super().itemChange(change, value)


class EdgeItem(QGraphicsPathItem):
    def __init__(self, source: PortItem, target: Optional[PortItem], is_branch: bool = False):
        super().__init__()
        self.source: Optional[PortItem] = source
        self.target: Optional[PortItem] = target
        self.temp_end: Optional[QPointF] = None
        self.is_branch = is_branch
        self.is_highlighted = False  # для фактического пути исполнения (зелёный)
        self._update_pen()
        self.setZValue(-0.5)
        self.setAcceptHoverEvents(True)
        if self.source:
            self.source.add_edge(self)
        if self.target:
            self.target.add_edge(self)
        self.update_path()

    def _update_pen(self):
        # если выделен путь — рисуем зелёным и толще
        if self.is_highlighted:
            self.setPen(QPen(PATH_EDGE, 4.0))
        else:
            color = BRANCH_EDGE if self.is_branch else EXEC_EDGE
            self.setPen(QPen(color, 2.0))

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(10)
        return stroker.createStroke(self.path())

    def set_highlighted(self, on: bool):
        self.is_highlighted = on
        self._update_pen()
        # Подсветим также концы (порты) и рамку нод, к которым примыкает путь
        try:
            if self.source:
                self.source.set_path_highlight(on)
                if isinstance(self.source.owner, NodeItem):
                    self.source.owner.set_exec_path_emphasis(on)
            if self.target:
                self.target.set_path_highlight(on)
                if isinstance(self.target.owner, NodeItem):
                    self.target.owner.set_exec_path_emphasis(on)
        except Exception:
            pass

    def set_target(self, t: Optional[PortItem]):
        if self.target is t:
            return
        if self.target:
            self.target.remove_edge(self)
        self.target = t
        if t:
            t.add_edge(self)
        self.update_path()

    def set_temp_end(self, p: Optional[QPointF]):
        self.temp_end = p
        self.update_path()

    def other_end(self, p: PortItem) -> Optional[PortItem]:
        if p is self.source:
            return self.target
        if p is self.target:
            return self.source
        return None

    def detach_from_ports(self):
        if self.source:
            self.source.remove_edge(self)
        if self.target:
            self.target.remove_edge(self)

    def destroy(self):
        try:
            self.detach_from_ports()
        except Exception:
            pass
        sc = self.scene()
        if sc:
            try:
                sc.removeItem(self)
            except Exception:
                pass

    def update_path(self):
        if self.source is None or self.source.scene() is None:
            return
        p1 = self.source.center_in_scene()
        if self.target and self.target.scene() is not None:
            p2 = self.target.center_in_scene()
        else:
            p2 = self.temp_end or p1

        path = QPainterPath(p1)
        dx = max(30.0, abs(p2.x() - p1.x()) * 0.5)
        c1 = QPointF(p1.x() + dx, p1.y())
        c2 = QPointF(p2.x() - dx, p2.y())
        path.cubicTo(c1, c2, p2)
        self.setPath(path)


# --- помогающие элементы для двойного клика на превью ---
class _PreviewRectItem(QGraphicsRectItem):
    def __init__(self, owner_node: "NodeItem"):
        super().__init__(owner_node)
        self._owner_node = owner_node

    def mouseDoubleClickEvent(self, event):
        cb = getattr(self._owner_node, "_on_double_click", None)
        if callable(cb):
            try:
                cb(self._owner_node)
                event.accept()
                return
            except Exception:
                pass
        super().mouseDoubleClickEvent(event)


class _PreviewTextItem(QGraphicsTextItem):
    def __init__(self, owner_node: "NodeItem"):
        super().__init__(owner_node)
        self._owner_node = owner_node

    def mouseDoubleClickEvent(self, event):
        cb = getattr(self._owner_node, "_on_double_click", None)
        if callable(cb):
            try:
                cb(self._owner_node)
                event.accept()
                return
            except Exception:
                pass
        super().mouseDoubleClickEvent(event)


BTN_H   = 16   # высота одной кнопки провала
BTN_GAP = 2    # вертикальный зазор между кнопками
BTN_PAD = 5    # отступ сверху зоны кнопок от разделителя

# Цвета кнопок провала
BTN_SCRIPT_BG    = QColor("#1a3a22")
BTN_SCRIPT_HOVER = QColor("#2a5a35")
BTN_SCRIPT_BORDER= QColor("#2d7a44")
BTN_SCRIPT_TEXT  = QColor("#44ee77")
BTN_FILE_BG      = QColor("#1a2d3a")
BTN_FILE_HOVER   = QColor("#2a4a5a")
BTN_FILE_BORDER  = QColor("#2d5a7a")
BTN_FILE_TEXT    = QColor("#66aadd")


class DrilldownButton(QGraphicsRectItem):
    """Кликабельная кнопка провала внутри NodeItem."""

    def __init__(self, label: str, tooltip: str, kind: str, callback: Callable, owner: "NodeItem"):
        super().__init__(owner)
        self._label    = label
        self._kind     = kind      # "script" | "file"
        self._callback = callback
        self._hovered  = False
        self.setToolTip(tooltip)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(8)
        self._refresh()

    def _refresh(self):
        if self._kind == "script":
            bg     = BTN_SCRIPT_HOVER if self._hovered else BTN_SCRIPT_BG
            border = BTN_SCRIPT_BORDER
        else:
            bg     = BTN_FILE_HOVER   if self._hovered else BTN_FILE_BG
            border = BTN_FILE_BORDER
        self.setBrush(QBrush(bg))
        self.setPen(QPen(border, 1.0))

    def hoverEnterEvent(self, event):
        self._hovered = True
        self._refresh()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self._refresh()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            try:
                self._callback()
            except Exception:
                pass
            event.accept()
        else:
            super().mousePressEvent(event)

    # Не даём ноде двигаться при клике на кнопку
    def mouseReleaseEvent(self, event):
        event.accept()

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        r = self.rect()
        icon = "⇒ " if self._kind == "script" else "↗ "
        text_color = BTN_SCRIPT_TEXT if self._kind == "script" else BTN_FILE_TEXT
        f = QFont()
        f.setPointSize(7)
        painter.setFont(f)
        painter.setPen(QPen(text_color))
        painter.drawText(
            r.adjusted(5, 0, -4, 0),
            Qt.AlignVCenter | Qt.AlignLeft,
            icon + self._label,
        )


class NodeItem(QGraphicsRectItem):
    WIDTH = 300
    HEIGHT = 96
    PADDING = 6

    def __init__(self, title: str, subtitle: str, payload, bg: QColor = NODE_BG,
                 node_type: str = ""):
        super().__init__(0, 0, NodeItem.WIDTH, NodeItem.HEIGHT)
        self.title = title
        self.subtitle = subtitle
        self.description = ""
        self.payload = payload
        self.node_type = node_type
        self.custom_color: Optional[QColor] = None
        self._default_bg = bg
        self._in_ports: List[PortItem] = []
        self._out_ports: List[PortItem] = []
        self._port_labels_internal: Dict[str, QGraphicsSimpleTextItem] = {}
        self._on_moved: Optional[Callable[["NodeItem"], None]] = None
        self._on_color_changed: Optional[Callable[["NodeItem"], None]] = None
        self._on_double_click: Optional[Callable[["NodeItem"], None]] = None

        # Превью (кармашек)
        self._prev_bg_item: Optional[_PreviewRectItem] = None
        self._prev_text_item: Optional[_PreviewTextItem] = None

        # Подчёркивание ноды как части пути
        self._exec_path_emph: bool = False

        # Кнопки провала в нижней части ноды
        self._drilldown_btns: List[DrilldownButton] = []
        self._drilldown_zone_h: int = 0   # зарезервированная высота под кнопки
        self._base_rect_h: float = 0      # исходная высота без кнопок

        # "Провал" при двойном клике (старый способ): "" / "file" / "script"
        self.drilldown_type: str = ""

        self.setBrush(QBrush(bg))
        self.setPen(QPen(NODE_BORDER, 1.0))
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

    # ---- preview pocket ----
    def _truncate(self, s: str, limit: int = 120) -> str:
        if s is None:
            return ""
        return s if len(s) <= limit else s[:limit] + "…"

    def _enrich_if_preview(self, text: str) -> str:
        """
        Заменяет 'IF -> branch_0' на 'IF → <условие> (branch_0)' и 'IF -> else' на 'IF → Иначе'
        используя подписи веток у портов.
        """
        if not text or "IF" not in text:
            return text
        t = text.strip()
        lower = t.lower()
        if "if -> branch_" in lower:
            # вытащим ключ branch_X
            import re
            m = re.search(r"if\s*->\s*(branch_\d+)", lower)
            if m:
                key = m.group(1)
                lab = self._port_labels_internal.get(key)
                cond = lab.text() if isinstance(lab, QGraphicsSimpleTextItem) else ""
                cond = self._truncate(cond, 96)
                if cond:
                    return f"IF → {cond} ({key})"
                else:
                    return f"IF → ({key})"
        if "if -> else" in lower:
            return "IF → Иначе"
        return text

    def set_preview_text(self, text: Optional[str], error: bool = False):
        if not text:
            self.clear_preview()
            return

        # Расширим превью IF для понятности
        text = self._enrich_if_preview(text)

        if self._prev_text_item is None:
            self._prev_text_item = _PreviewTextItem(self)
            f = self._prev_text_item.font()
            f.setPointSize(7)  # компактнее
            self._prev_text_item.setFont(f)
            self._prev_text_item.setDefaultTextColor(PREV_TEXT)
            self._prev_text_item.setZValue(5)

        if self._prev_bg_item is None:
            self._prev_bg_item = _PreviewRectItem(self)
            self._prev_bg_item.setZValue(-0.2)

        # текст (сжато)
        max_w = self.rect().width() - 12
        self._prev_text_item.setTextWidth(max_w)
        self._prev_text_item.setPlainText(text)

        # позиционирование (ближе к ноде)
        top_y = self.rect().bottom() + 4
        self._prev_text_item.setPos(self.rect().left() + 6, top_y + 4)

        # фон по размеру текста (компактнее)
        br = self._prev_text_item.boundingRect()
        rect = QRectF(self.rect().left() + 2, top_y, self.rect().width() - 4, br.height() + 8)
        pen = QPen(QColor("#AA3333") if error else PREV_BR, 1.0)
        self._prev_bg_item.setPen(pen)
        self._prev_bg_item.setBrush(QBrush(QColor(48, 48, 48, 230) if error else PREV_BG))
        self._prev_bg_item.setRect(rect)

    def clear_preview(self):
        if self._prev_text_item:
            try:
                self.scene().removeItem(self._prev_text_item) if self.scene() else None
            except Exception:
                pass
            self._prev_text_item = None
        if self._prev_bg_item:
            try:
                self.scene().removeItem(self._prev_bg_item) if self.scene() else None
            except Exception:
                pass
            self._prev_bg_item = None

    # ---- exec path emphasis ----
    def set_exec_path_emphasis(self, on: bool):
        self._exec_path_emph = on
        self.update()

    # ---- meta ----
    def set_description(self, desc: str):
        self.description = desc
        tooltip_parts = [self.title]
        if self.subtitle:
            tooltip_parts.append(self.subtitle)
        if desc:
            tooltip_parts.append(f"\n{desc}")
        self.setToolTip("\n".join(tooltip_parts))

    # ---------- drilldown buttons ----------
    def set_drilldown_buttons(self, buttons: List[tuple]):
        """
        buttons: список (label, tooltip, kind, callback)
          label    — короткое имя файла
          tooltip  — полный путь
          kind     — "script" | "file"
          callback — callable()
        Расширяет ноду снизу под кнопки.
        """
        # Удалить старые
        for btn in self._drilldown_btns:
            try:
                if btn.scene():
                    btn.scene().removeItem(btn)
            except Exception:
                pass
        self._drilldown_btns.clear()

        # Вернуть ноду к базовой высоте
        r = self.rect()
        base_h = self._base_rect_h if self._base_rect_h > 0 else r.height()
        self._base_rect_h = base_h
        self._drilldown_zone_h = 0

        if not buttons:
            self.setRect(0, 0, r.width(), base_h)
            self._layout_ports()
            return

        n = len(buttons)
        zone_h = BTN_PAD + n * BTN_H + (n - 1) * BTN_GAP + BTN_PAD
        self._drilldown_zone_h = zone_h
        new_h = base_h + zone_h
        self.setRect(0, 0, r.width(), new_h)

        # Создать кнопки
        btn_w = r.width() - 10
        y = base_h + BTN_PAD
        for label, tip, kind, cb in buttons:
            btn = DrilldownButton(label, tip, kind, cb, self)
            btn.setRect(5, y, btn_w, BTN_H)
            self._drilldown_btns.append(btn)
            y += BTN_H + BTN_GAP

        self._layout_ports()

    def set_custom_color(self, color: Optional[QColor]):
        self.custom_color = color
        if color:
            self.setBrush(QBrush(color))
        else:
            self.setBrush(QBrush(self._default_bg))
        self.update()
        if self._on_color_changed:
            try:
                self._on_color_changed(self)
            except Exception:
                pass

    def get_custom_color(self) -> Optional[QColor]:
        return self.custom_color

    def set_color_changed_callback(self, cb: Optional[Callable[["NodeItem"], None]]):
        self._on_color_changed = cb

    def set_double_click_callback(self, cb: Optional[Callable[["NodeItem"], None]]):
        self._on_double_click = cb

    def mouseDoubleClickEvent(self, event):
        if self._on_double_click:
            try:
                self._on_double_click(self)
                event.accept()
                return
            except Exception:
                pass
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        color_menu = menu.addMenu("Цвет ноды")
        colors = [
            ("По умолчанию", None),
            ("Красный", QColor("#4A1A1A")),
            ("Зелёный", QColor("#1A4A1A")),
            ("Синий", QColor("#1A1A4A")),
            ("Жёлтый", QColor("#4A4A1A")),
            ("Фиолетовый", QColor("#3A1A4A")),
            ("Бирюзовый", QColor("#1A4A4A")),
        ]
        for name, color in colors:
            action = color_menu.addAction(name)
            if color:
                pixmap = self._create_color_pixmap(color)
                from PySide6.QtGui import QIcon
                action.setIcon(QIcon(pixmap))
            action.triggered.connect(lambda checked=False, c=color: self.set_custom_color(c))
        color_menu.addSeparator()
        custom_action = color_menu.addAction("Выбрать цвет...")
        custom_action.triggered.connect(self._pick_custom_color)
        menu.exec(event.screenPos())
        event.accept()

    def _create_color_pixmap(self, color: QColor):
        from PySide6.QtGui import QPixmap, QPainter
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor("#666666"), 1))
        painter.drawRect(1, 1, 14, 14)
        painter.end()
        return pixmap

    def _pick_custom_color(self):
        color = QColorDialog.getColor(self.custom_color if self.custom_color else self._default_bg, None, "Выбрать цвет ноды")
        if color.isValid():
            self.set_custom_color(color)

    # ---------- ports ----------
    def add_in_port(self, key: str, label: str) -> PortItem:
        p = PortItem(self, key, True)
        p.setToolTip(label)
        self._in_ports.append(p)
        self._layout_ports()
        return p

    def add_out_port(self, key: str, label: str) -> PortItem:
        p = PortItem(self, key, False)
        p.setToolTip(label)
        self._out_ports.append(p)
        if key != "exec":
            lab = QGraphicsSimpleTextItem(label, self)
            lab.setBrush(QBrush(TEXT_SECONDARY))
            f = lab.font(); f.setPointSize(8); lab.setFont(f)
            self._port_labels_internal[key] = lab
            lab.setAcceptHoverEvents(True)
            lab.setData(0, key)
        self._layout_ports()
        return p

    def in_port(self, key: str) -> Optional[PortItem]:
        for p in self._in_ports:
            if p.key == key:
                return p
        return None

    def out_port(self, key: str) -> Optional[PortItem]:
        for p in self._out_ports:
            if p.key == key:
                return p
        return None

    def in_ports(self) -> List[PortItem]:
        return self._in_ports

    def out_ports(self) -> List[PortItem]:
        return self._out_ports

    def set_subtitle(self, txt: str):
        self.subtitle = txt
        self.update()

    def set_move_callback(self, cb: Optional[Callable[["NodeItem"], None]]):
        self._on_moved = cb

    def highlight_branch(self, port_key: str, on: bool):
        port = self.out_port(port_key)
        if port:
            port.set_highlighted(on)
            for edge in port.edges:
                edge.set_highlighted(on)

    # ---------- painting ----------
    def paint(self, painter, option, widget=None):
        r = self.rect()
        radius = 8.0

        # 1. Тело ноды — закруглённый прямоугольник #202020
        if self._exec_path_emph:
            border_pen = QPen(PATH_NODE_BORDER, 2.6)
        else:
            border_pen = QPen(NODE_SELECTED if self.isSelected() else NODE_BORDER,
                              1.5 if self.isSelected() else 1.0)
        body_color = self.custom_color if self.custom_color else NODE_BG
        painter.setPen(border_pen)
        painter.setBrush(QBrush(body_color))
        painter.drawRoundedRect(r, radius, radius)

        # 2. Шапка с градиентом по типу ноды (только если тип задан)
        style = NODE_TYPE_STYLES.get(self.node_type)
        if style:
            emoji, dark_hex, light_hex = style
            # Путь для шапки: скруглённые верхние углы, плоское дно
            hp = QPainterPath()
            hp.moveTo(r.left() + radius, r.top())
            hp.lineTo(r.right() - radius, r.top())
            hp.quadTo(r.right(), r.top(), r.right(), r.top() + radius)
            hp.lineTo(r.right(), r.top() + HEADER_H)
            hp.lineTo(r.left(), r.top() + HEADER_H)
            hp.lineTo(r.left(), r.top() + radius)
            hp.quadTo(r.left(), r.top(), r.left() + radius, r.top())
            hp.closeSubpath()

            grad = QLinearGradient(0, r.top(), 0, r.top() + HEADER_H)
            grad.setColorAt(0, QColor(light_hex))
            grad.setColorAt(1, QColor(dark_hex))
            painter.setPen(Qt.NoPen)
            painter.fillPath(hp, QBrush(grad))

            # Разделительная линия под шапкой
            painter.setPen(QPen(QColor(dark_hex).darker(120), 1))
            painter.drawLine(
                int(r.left()), int(r.top() + HEADER_H),
                int(r.right()), int(r.top() + HEADER_H)
            )

            # Эмодзи в шапке (компактно)
            f_emoji = QFont()
            f_emoji.setPointSize(11)
            painter.setFont(f_emoji)
            painter.setPen(QPen(TEXT_FG))
            emoji_rect = QRectF(r.left() + 4, r.top(), 20, HEADER_H)
            painter.drawText(emoji_rect, Qt.AlignVCenter | Qt.AlignLeft, emoji)

            # Заголовок типа в шапке (более компактный)
            f_title = QFont()
            f_title.setBold(True)
            f_title.setPointSize(7)
            painter.setFont(f_title)
            painter.setPen(QPen(TEXT_FG))
            title_rect = QRectF(r.left() + 24, r.top(), r.width() - 28, HEADER_H)
            painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, self.title)

            # Подзаголовок в контентной зоне (сжато)
            if self.subtitle:
                f_sub = QFont()
                f_sub.setPointSize(7)
                painter.setFont(f_sub)
                painter.setPen(QPen(TEXT_SECONDARY))
                sub_rect = r.adjusted(self.PADDING, HEADER_H + 3, -self.PADDING, -self.PADDING)
                painter.drawText(sub_rect, Qt.AlignTop | Qt.AlignLeft, self.subtitle)

            # Значок провала в правом нижнем углу
            if self.drilldown_type == "script":
                # Скрипт — пульсирующий зелёный значок «⇒ скрипт»
                badge_color = QColor("#22dd66")
                badge_text = "⇒"
            elif self.drilldown_type == "file":
                # Просто файл — бледно-синий значок «↗»
                badge_color = QColor("#5599cc")
                badge_text = "↗"
            else:
                badge_color = None
                badge_text = ""

            if badge_color and badge_text:
                f_badge = QFont()
                f_badge.setPointSize(9)
                f_badge.setBold(True)
                painter.setFont(f_badge)
                painter.setPen(QPen(badge_color))
                # Значок чуть выше зоны кнопок, если кнопки есть
                badge_y = r.bottom() - self._drilldown_zone_h - 18
                badge_rect = QRectF(r.right() - 22, badge_y, 18, 16)
                painter.drawText(badge_rect, Qt.AlignVCenter | Qt.AlignRight, badge_text)

            # Разделитель перед зоной кнопок провала
            if self._drilldown_zone_h > 0:
                sep_y = r.bottom() - self._drilldown_zone_h
                painter.setPen(QPen(QColor("#333333"), 1))
                painter.drawLine(
                    int(r.left() + 4), int(sep_y),
                    int(r.right() - 4), int(sep_y),
                )
        else:
            # Fallback: старый стиль без шапки
            painter.setPen(QPen(TEXT_FG))
            f = QFont(); f.setBold(True); f.setPointSize(9)
            painter.setFont(f)
            painter.drawText(
                r.adjusted(self.PADDING, self.PADDING, -self.PADDING, -self.PADDING),
                Qt.AlignTop | Qt.AlignLeft,
                self.title,
            )
            if self.subtitle:
                f2 = QFont(); f2.setPointSize(8)
                painter.setFont(f2)
                painter.setPen(QPen(TEXT_SECONDARY))
                painter.drawText(
                    r.adjusted(self.PADDING, 26, -self.PADDING, -self.PADDING),
                    Qt.AlignTop | Qt.AlignLeft,
                    self.subtitle,
                )

    def _layout_ports(self):
        r = self.rect()

        # inputs
        if self._in_ports:
            if len(self._in_ports) == 1 or all(p.key == "exec" for p in self._in_ports):
                p = self._in_ports[0]
                y = r.center().y()
                p.setPos(r.left(), y)
            else:
                step = r.height() / (len(self._in_ports) + 1)
                for i, p in enumerate(self._in_ports, start=1):
                    y = r.top() + i * step
                    p.setPos(r.left(), y)

        # outputs
        exec_port = None
        branch_ports: List[PortItem] = []
        for p in self._out_ports:
            if p.key == "exec":
                exec_port = p
            elif p.key.startswith("branch_") or p.key == "else":
                branch_ports.append(p)

        if exec_port is not None:
            y = r.top() + 18
            exec_port.setPos(r.right(), y)

        if branch_ports:
            top_zone = r.top() + 40
            # Не заходим в зону кнопок провала
            bottom = r.bottom() - 8 - self._drilldown_zone_h
            n = len(branch_ports)
            if n == 1:
                y = (top_zone + bottom) * 0.5
                branch_ports[0].setPos(r.right(), y)
                lab = self._port_labels_internal.get(branch_ports[0].key)
                if lab:
                    br = lab.boundingRect()
                    lab.setPos(r.right() - br.width() - 16, y - br.height() / 2)
            else:
                total_h = max(1.0, bottom - top_zone)
                step = total_h / (n + 1)
                for i, p in enumerate(branch_ports, 1):
                    y = top_zone + i * step
                    p.setPos(r.right(), y)
                    lab = self._port_labels_internal.get(p.key)
                    if lab:
                        br = lab.boundingRect()
                        lab.setPos(r.right() - br.width() - 16, y - br.height() / 2)

        for p in self._in_ports + self._out_ports:
            for e in list(p.edges):
                e.update_path()

    def mousePressEvent(self, event):
        for key, lab in self._port_labels_internal.items():
            if lab.contains(lab.mapFromScene(event.scenePos())):
                self.highlight_branch(key, True)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        for key in self._port_labels_internal.keys():
            self.highlight_branch(key, False)
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for p in self._in_ports + self._out_ports:
                for e in list(p.edges):
                    e.update_path()
            if self._on_moved:
                try:
                    self._on_moved(self)
                except Exception:
                    pass
        return super().itemChange(change, value)