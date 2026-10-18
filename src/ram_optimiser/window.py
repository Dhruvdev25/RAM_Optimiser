"""Premium dark Qt interface and event-driven application shell."""

from __future__ import annotations

import os
import sys
import time
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize, QThreadPool
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap, QPainter, QAction
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QColorDialog, QComboBox,
    QDialog, QDialogButtonBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSpinBox, QStackedWidget,
    QStyle, QSystemTrayIcon, QTableWidget, QTableWidgetItem, QTextEdit, QToolButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__
from .core import format_bytes
from .core import OperationGate
from .history import HistoryStore
from .services import (
    ProcessRecord, close_process, collect_process_names, collect_snapshot, collect_top_processes, inspect_process, list_processes,
    run_boost, set_run_at_logon, set_startup_entry, startup_entries, trim_process,
)
from .settings import Settings, SettingsStore
from .widgets import (
    GaugeWidget, HistoryChart, LogoMark, MetricTile, SparklineWidget,
    add_section_title, make_gauge_card, panel,
)
from .workers import Worker


NAV_ITEMS = [
    ("Home Dashboard", "\ue80f"), ("PC Monitor", "\ue9d9"),
    ("Smart Boost", "\uea80"), ("Game Mode", "\ue7fc"),
    ("Process Manager", "\ue9f5"), ("Startup Apps", "\ue7e7"),
    ("Performance History", "\ue9d2"), ("Settings", "\ue713"),
]


def _icon_for(glyph: str, color="#8ea4b9") -> QIcon:
    pix = QPixmap(24, 24)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setPen(QColor(color))
    painter.setFont(QFont("Segoe MDL2 Assets", 15))
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return QIcon(pix)


def _make_scroll_page():
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    container = QWidget()
    container.setObjectName("pageContainer")
    container.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(28, 25, 28, 28)
    layout.setSpacing(18)
    layout.addStretch(0)
    scroll.setWidget(container)
    return scroll, container, layout


def _label(text, object_name="muted", parent=None):
    result = QLabel(text, parent)
    result.setObjectName(object_name)
    result.setWordWrap(True)
    return result


def _button(text: str, kind="secondary", parent=None):
    button = QPushButton(text, parent)
    button.setObjectName(kind)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setMinimumHeight(36)
    return button


class SortableItem(QTableWidgetItem):
    def __lt__(self, other):
        left = self.data(Qt.ItemDataRole.UserRole + 1)
        right = other.data(Qt.ItemDataRole.UserRole + 1)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left < right
        return self.text().casefold() < other.text().casefold()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._smoke_test = os.environ.get("RAM_OPTIMISER_SMOKE_TEST") == "1"
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.history = HistoryStore(retention_days=self.settings.history_retention_days)
        self.thread_pool = QThreadPool.globalInstance()
        self._snapshot_busy = False
        self._process_busy = False
        self._process_names_busy = False
        self._top_processes_busy = False
        self._startup_busy = False
        self._boost_busy = False
        self._operation_gate = OperationGate()
        self._last_auto_run = 0.0
        self._last_auto_check = 0.0
        self._pressure_notified = False
        self._last_snapshot = None
        self._process_records: list[ProcessRecord] = []
        self._process_names: list[str] = []
        self._top_processes: list[dict] = []
        self._session_id = None
        self._session_started = None
        self._session_elapsed = 0
        self._current_page = 0
        self._worker_refs = []
        self._responsive_layouts = []
        self._closing_wait = False
        self._force_exit = False
        self._build_ui()
        self._build_pages()
        self._wire_ui()
        self._apply_theme()
        if not self._smoke_test:
            self._init_tray()
        self._monitor_timer = QTimer(self)
        self._monitor_timer.timeout.connect(self._request_snapshot)
        if not self._smoke_test:
            self._monitor_timer.start(max(1, self.settings.refresh_seconds) * 1000)
            self._request_snapshot()
        self._process_names_timer = QTimer(self)
        self._process_names_timer.timeout.connect(self._request_process_names)
        if not self._smoke_test:
            self._process_names_timer.start(max(2, self.settings.refresh_seconds * 2) * 1000)
        self._top_process_timer = QTimer(self)
        self._top_process_timer.timeout.connect(self._request_top_processes)
        if not self._smoke_test:
            self._top_process_timer.start(60_000)
            self._request_process_names()
            self._request_top_processes()
        self._game_timer = QTimer(self)
        self._game_timer.timeout.connect(self._update_game_session_display)
        if not self._smoke_test:
            self._game_timer.start(1000)
        QApplication.instance().aboutToQuit.connect(self._shutdown_workers)
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1040, 720)
        self.resize(1440, 900)

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("appRoot")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(226)
        side = QVBoxLayout(self.sidebar)
        self.sidebar_layout = side
        side.setContentsMargins(16, 18, 14, 18)
        side.setSpacing(6)
        brand = QHBoxLayout()
        brand.setSpacing(11)
        brand.addWidget(LogoMark())
        brand_text = QVBoxLayout()
        brand_title = QLabel("RAM Optimiser")
        self.brand_title_label = brand_title
        brand_title.setObjectName("brandTitle")
        brand_sub = QLabel("SYSTEM PERFORMANCE")
        self.brand_sub_label = brand_sub
        brand_sub.setObjectName("brandSub")
        brand_text.addWidget(brand_title)
        brand_text.addWidget(brand_sub)
        brand.addLayout(brand_text, 1)
        side.addLayout(brand)
        side.addSpacing(21)
        nav_caption = QLabel("WORKSPACE")
        self.nav_caption_label = nav_caption
        nav_caption.setObjectName("brandSub")
        nav_caption.setContentsMargins(10, 0, 0, 7)
        side.addWidget(nav_caption)
        self.nav_buttons = []
        for index, (title, glyph) in enumerate(NAV_ITEMS):
            button = QPushButton(title)
            button.setObjectName("navButton")
            button.setIcon(_icon_for(glyph))
            button.setIconSize(QSize(19, 19))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(42)
            button.clicked.connect(lambda checked=False, i=index: self._navigate(i))
            side.addWidget(button)
            self.nav_buttons.append(button)
        side.addStretch(1)
        local_box, local_layout = panel(padding=12)
        self.local_status_box = local_box
        local_box.setObjectName("localStatus")
        local_layout.setSpacing(5)
        local_layout.addWidget(_label("LOCAL AND PRIVATE", "eyebrow"))
        local_layout.addWidget(_label("Metrics and history stay on this PC.", "muted"))
        side.addWidget(local_box)
        side.addSpacing(9)
        version_label = QLabel(f"Version {__version__}")
        self.version_label = version_label
        version_label.setObjectName("brandSub")
        version_label.setContentsMargins(10, 0, 0, 0)
        side.addWidget(version_label)
        outer.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("mainContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.topbar = QFrame()
        self.topbar.setObjectName("topbar")
        top_layout = QHBoxLayout(self.topbar)
        top_layout.setContentsMargins(28, 15, 28, 14)
        top_layout.setSpacing(12)
        page_text = QVBoxLayout()
        self.page_title = QLabel("Home Dashboard")
        self.page_title.setObjectName("topTitle")
        self.page_subtitle = QLabel("A live view of your computer")
        self.page_subtitle.setObjectName("muted")
        page_text.addWidget(self.page_title)
        page_text.addWidget(self.page_subtitle)
        top_layout.addLayout(page_text, 1)
        self.live_badge = QLabel("●  CONNECTING")
        self.live_badge.setObjectName("statusBadge")
        top_layout.addWidget(self.live_badge)
        self.global_refresh = _button("Refresh", "secondary")
        self.global_refresh.setIcon(_icon_for("\ue72c", "#d2e3f0"))
        self.global_refresh.clicked.connect(self._request_snapshot)
        top_layout.addWidget(self.global_refresh)
        content_layout.addWidget(self.topbar)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        outer.addWidget(content, 1)
        self.setCentralWidget(root)

    def _build_pages(self):
        self.pages = []
        for _ in NAV_ITEMS:
            scroll, container, layout = _make_scroll_page()
            self.pages.append((scroll, container, layout))
            self.stack.addWidget(scroll)
        self._build_home()
        self._build_monitor()
        self._build_boost()
        self._build_game()
        self._build_processes()
        self._build_startup()
        self._build_history()
        self._build_settings()

    def _register_responsive_grid(self, layout, widgets, wide_columns, narrow_columns):
        self._responsive_layouts.append((layout, list(widgets), wide_columns, narrow_columns, wide_columns))

    def _build_home(self):
        _, container, layout = self.pages[0]
        layout.setSpacing(17)
        hero = QHBoxLayout()
        welcome = QVBoxLayout()
        welcome.addWidget(_label("Your PC, at a glance", "heroTitle"))
        self.home_status = _label("Live system measurements will appear here.", "muted")
        welcome.addWidget(self.home_status)
        hero.addLayout(welcome, 1)
        self.system_chip = _label("●  Local monitoring", "pill")
        hero.addWidget(self.system_chip, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(hero)

        self.home_gauges = {}
        grid = QGridLayout()
        grid.setSpacing(14)
        gauge_cards = []
        for pos, (key, title, icon, color) in enumerate([
            ("cpu", "CPU", "◉", "#4dbbff"), ("gpu", "GPU", "◈", "#9079ff"),
            ("ram", "Memory", "▤", "#42c9b4"), ("storage", "Storage", "▦", "#f5a84a"),
        ]):
            card, gauge = make_gauge_card(title, icon, color)
            self.home_gauges[key] = gauge
            grid.addWidget(card, pos // 2, pos % 2)
            gauge_cards.append(card)
        self._register_responsive_grid(grid, gauge_cards, 2, 1)
        layout.addLayout(grid)

        overview, over = panel(padding=16)
        over.addWidget(_label("SYSTEM OVERVIEW", "eyebrow"))
        metrics_row = QGridLayout()
        self.home_tiles = {}
        metric_widgets = []
        for key, title in (("processor", "PROCESSOR"), ("gpu_name", "GRAPHICS"),
                           ("memory", "MEMORY"), ("processes", "PROCESSES"),
                           ("computer", "DEVICE")):
            tile = MetricTile(title, "—")
            self.home_tiles[key] = tile
            metric_widgets.append(tile)
            metrics_row.addWidget(tile, 0, len(metric_widgets) - 1)
        self._register_responsive_grid(metrics_row, metric_widgets, 5, 3)
        over.addLayout(metrics_row)
        layout.addWidget(overview)

        top_card, top_layout = panel(padding=14)
        top_layout.addWidget(_label("TOP MEMORY USERS", "eyebrow"))
        self.home_top_processes = QTableWidget(0, 3)
        self.home_top_processes.setHorizontalHeaderLabels(["Application", "PID", "Working set"])
        self.home_top_processes.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.home_top_processes.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.home_top_processes.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.home_top_processes.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.home_top_processes.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.home_top_processes.setMaximumHeight(194)
        self.home_top_status = _label("Waiting for the first process scan…", "muted")
        top_layout.addWidget(self.home_top_status)
        top_layout.addWidget(self.home_top_processes)
        layout.addWidget(top_card)

        action_grid = QGridLayout()
        action_grid.setSpacing(14)
        action_cards = []
        self.home_boost_button = _button("Open Smart Boost  →", "primary")
        self.home_boost_button.clicked.connect(lambda: self._navigate(2))
        self.home_game_button = _button("Open Game Mode  →", "secondary")
        self.home_game_button.clicked.connect(lambda: self._navigate(3))
        for col, (title, description, button) in enumerate([
            ("Smart Boost", "Request conservative Windows working-set trims.", self.home_boost_button),
            ("Game Mode", "Track a game session and review background usage.", self.home_game_button),
        ]):
            card, card_layout = panel(padding=16)
            card_layout.addWidget(_label(title, "cardTitle"))
            card_layout.addWidget(_label(description, "muted"))
            card_layout.addWidget(button)
            action_grid.addWidget(card, 0, col)
            action_cards.append(card)
        self._register_responsive_grid(action_grid, action_cards, 2, 1)
        layout.addLayout(action_grid)
        layout.addStretch(1)

    def _build_monitor(self):
        _, _, layout = self.pages[1]
        add_section_title(layout, "PC Monitor", "Current measurements come from Windows and supported hardware APIs. Unsupported sensors are shown as unavailable.")
        grid = QGridLayout()
        self.monitor_tiles = {}
        monitor_tile_widgets = []
        keys = [
            ("cpu", "CPU utilization"), ("cpu_temp", "CPU temperature"),
            ("ram_total", "Total memory"), ("ram_used", "Used memory"),
            ("ram_available", "Available memory"), ("gpu", "GPU utilization"),
            ("gpu_temp", "GPU temperature"), ("vram", "VRAM"),
            ("storage", "Selected drive"), ("process_count", "Running processes"),
        ]
        for index, (key, title) in enumerate(keys):
            tile = MetricTile(title.upper(), "Unavailable")
            self.monitor_tiles[key] = tile
            monitor_tile_widgets.append(tile)
            grid.addWidget(tile, index // 5, index % 5)
        self._register_responsive_grid(grid, monitor_tile_widgets, 5, 3)
        layout.addLayout(grid)
        graphs = QGridLayout()
        self.monitor_ram_chart = HistoryChart(color="#45c9b4")
        self.monitor_cpu_chart = HistoryChart(color="#48b9ff")
        graph_cards = []
        for index, (title, chart) in enumerate((("Memory utilization", self.monitor_ram_chart), ("CPU utilization", self.monitor_cpu_chart))):
            card, card_layout = panel()
            card_layout.addWidget(_label(title, "cardTitle"))
            card_layout.addWidget(chart)
            graphs.addWidget(card, 0, index)
            graph_cards.append(card)
        self._register_responsive_grid(graphs, graph_cards, 2, 1)
        layout.addLayout(graphs)
        info, info_layout = panel()
        info_layout.addWidget(_label("DEVICE DETAILS", "eyebrow"))
        self.monitor_details = _label("Waiting for the first system sample…", "muted")
        info_layout.addWidget(self.monitor_details)
        layout.addWidget(info)
        layout.addStretch(1)

    def _build_boost(self):
        _, _, layout = self.pages[2]
        add_section_title(layout, "Smart Boost", "A working-set trim asks Windows to discard some process memory pages. Windows remains in control; available RAM can stay unchanged or move either way.")
        note, note_layout = panel(padding=14)
        note_layout.addWidget(_label("No app closing", "cardTitle"))
        note_layout.addWidget(_label("Boost never terminates applications. Some apps may reload data after trimming. Results show measured before-and-after available memory, not an estimate of bytes reclaimed.", "muted"))
        layout.addWidget(note)
        grid = QGridLayout()
        grid.setSpacing(14)
        self.boost_buttons = {}
        boost_cards = []
        modes = [
            ("One-Click Boost", "Conservative pass", "Eligible user processes above 80 MiB; at most 18 trim requests."),
            ("Quick Boost", "Small pass", "The largest eligible user processes above 100 MiB; at most 6 requests."),
            ("Deep Boost", "Broader pass", "More eligible user processes above 35 MiB; up to 60 requests. Trimmed apps may reload more data."),
        ]
        for index, (mode, heading, desc) in enumerate(modes):
            card, card_layout = panel()
            card_layout.addWidget(_label(heading.upper(), "eyebrow"))
            card_layout.addWidget(_label(mode, "cardTitle"))
            card_layout.addWidget(_label(desc, "muted"))
            card_layout.addStretch(1)
            button = _button("Run " + mode, "primary" if index == 0 else "secondary")
            button.clicked.connect(lambda checked=False, m=mode: self._start_boost(m, automatic=False))
            card_layout.addWidget(button)
            self.boost_buttons[mode] = button
            grid.addWidget(card, 0, index)
            boost_cards.append(card)
        self._register_responsive_grid(grid, boost_cards, 3, 1)
        layout.addLayout(grid)
        self.boost_progress = QProgressBar()
        self.boost_progress.setRange(0, 1)
        self.boost_progress.setValue(0)
        self.boost_progress.setTextVisible(False)
        self.boost_progress.setFixedHeight(4)
        layout.addWidget(self.boost_progress)
        result_card, result_layout = panel()
        result_layout.addWidget(_label("LATEST RESULT", "eyebrow"))
        self.boost_result = _label("No Boost operation has run in this session.", "muted")
        result_layout.addWidget(self.boost_result)
        layout.addWidget(result_card)
        self.boost_recent = QTableWidget(0, 6)
        self.boost_recent.setHorizontalHeaderLabels(["Time", "Mode", "Available before", "Available after", "Trim requests", "Duration"])
        self.boost_recent.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.boost_recent.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.boost_recent.setMaximumHeight(220)
        history_card, history_layout = panel()
        history_layout.addWidget(_label("RECENT BOOST ACTIVITY", "eyebrow"))
        history_layout.addWidget(self.boost_recent)
        layout.addWidget(history_card)
        layout.addStretch(1)

    def _build_game(self):
        _, _, layout = self.pages[3]
        add_section_title(layout, "Game Mode", "Track a selected game, watch current system load, and review background applications. RAM Optimiser never closes apps automatically and cannot promise a frame-rate gain.")
        profile, profile_layout = panel()
        profile_layout.addWidget(_label("GAME PROFILE", "eyebrow"))
        saved_profiles = list(dict.fromkeys(self.settings.game_profiles + ([self.settings.game_executable] if self.settings.game_executable else [])))
        self.settings.game_profiles = saved_profiles
        profile_select_row = QHBoxLayout()
        self.game_profile_combo = QComboBox()
        for saved_path in saved_profiles:
            self.game_profile_combo.addItem(Path(saved_path).name or saved_path, saved_path)
            self.game_profile_combo.setItemData(self.game_profile_combo.count() - 1, saved_path, Qt.ItemDataRole.ToolTipRole)
        if self.settings.game_executable:
            self.game_profile_combo.setCurrentIndex(max(0, self.game_profile_combo.findData(self.settings.game_executable)))
        self.game_profile_combo.setEnabled(bool(saved_profiles))
        self.game_profile_combo.currentIndexChanged.connect(self._select_game_profile)
        profile_select_row.addWidget(self.game_profile_combo, 1)
        remove_profile = _button("Remove profile", "secondary")
        remove_profile.clicked.connect(self._remove_game_profile)
        profile_select_row.addWidget(remove_profile)
        profile_layout.addLayout(profile_select_row)
        profile_row = QHBoxLayout()
        self.game_path = QLineEdit(self.settings.game_executable)
        self.game_path.setPlaceholderText("Select a game executable to start session tracking")
        self.game_path.setReadOnly(True)
        profile_row.addWidget(self.game_path, 1)
        choose = _button("Choose executable…", "secondary")
        choose.clicked.connect(self._choose_game)
        profile_row.addWidget(choose)
        profile_layout.addLayout(profile_row)
        profile_layout.addWidget(_label("Detection matches the selected executable name among running processes. Background suggestions are informational; review them in Process Manager if you choose to close anything.", "muted"))
        layout.addWidget(profile)
        session, session_layout = panel(padding=17)
        session_layout.addWidget(_label("CURRENT SESSION", "eyebrow"))
        self.game_session_label = _label("No selected game is running.", "cardTitle")
        self.game_session_time = _label("00:00:00", "heroTitle")
        session_layout.addWidget(self.game_session_label)
        session_layout.addWidget(self.game_session_time)
        layout.addWidget(session)
        self.game_metrics = {}
        metric_row = QGridLayout()
        game_metric_widgets = []
        for key, title in (("cpu", "CPU"), ("gpu", "GPU"), ("ram", "MEMORY"),
                           ("vram", "VRAM"), ("temperature", "GPU TEMP"), ("cpu_temp", "CPU TEMP")):
            tile = MetricTile(title, "Unavailable")
            self.game_metrics[key] = tile
            game_metric_widgets.append(tile)
            metric_row.addWidget(tile, 0, len(game_metric_widgets) - 1)
        self._register_responsive_grid(metric_row, game_metric_widgets, 6, 3)
        layout.addLayout(metric_row)
        bg, bg_layout = panel()
        bg_layout.addWidget(_label("HIGH-MEMORY BACKGROUND APPS", "eyebrow"))
        self.game_background = _label("Waiting for process measurements…", "muted")
        bg_layout.addWidget(self.game_background)
        layout.addWidget(bg)
        self.game_sessions = QTableWidget(0, 3)
        self.game_sessions.setHorizontalHeaderLabels(["Started", "Game", "Duration"])
        self.game_sessions.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.game_sessions.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.game_sessions.setMaximumHeight(220)
        session_card, session_card_layout = panel()
        session_card_layout.addWidget(_label("RECENT GAME SESSIONS", "eyebrow"))
        session_card_layout.addWidget(self.game_sessions)
        layout.addWidget(session_card)
        layout.addStretch(1)

    def _build_processes(self):
        _, _, layout = self.pages[4]
        add_section_title(layout, "Process Manager", "Actions apply only to selected rows and revalidate each PID against its creation time before acting. Windows essentials and RAM Optimiser are always protected.")
        controls = QHBoxLayout()
        self.process_search = QLineEdit()
        self.process_search.setPlaceholderText("Search process name or PID…")
        self.process_search.textChanged.connect(self._filter_process_table)
        controls.addWidget(self.process_search, 1)
        self.process_count_label = _label("0 selected", "pill")
        controls.addWidget(self.process_count_label)
        refresh = _button("Refresh", "secondary")
        refresh.clicked.connect(self._request_processes)
        controls.addWidget(refresh)
        layout.addLayout(controls)
        self.process_status_label = _label("Process details load when you open this page.", "muted")
        layout.addWidget(self.process_status_label)
        self.process_table = QTableWidget(0, 6)
        self.process_table.setHorizontalHeaderLabels(["Process", "PID", "Memory", "CPU", "Status", "Protection"])
        self.process_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.process_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.process_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.process_table.setSortingEnabled(True)
        self.process_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 6):
            self.process_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.process_table.itemSelectionChanged.connect(self._update_selected_count)
        self.process_table.cellDoubleClicked.connect(lambda row, _col: self._inspect_selected_row(row))
        layout.addWidget(self.process_table, 1)
        actions = QHBoxLayout()
        self.trim_process_button = _button("Trim memory", "secondary")
        self.trim_process_button.clicked.connect(self._trim_selected)
        actions.addWidget(self.trim_process_button)
        self.close_process_button = _button("Close gracefully…", "secondary")
        self.close_process_button.clicked.connect(lambda: self._close_selected(force=False))
        actions.addWidget(self.close_process_button)
        self.force_process_button = _button("Force terminate…", "danger")
        self.force_process_button.clicked.connect(lambda: self._close_selected(force=True))
        actions.addWidget(self.force_process_button)
        layout.addLayout(actions)
        layout.addWidget(_label("Trimming is a Windows hint and may make the app reload data. Graceful close can prompt the app to save. Force termination can lose unsaved work. Large memory use alone never triggers an action.", "muted"))

    def _build_startup(self):
        _, _, layout = self.pages[5]
        add_section_title(layout, "Startup Apps", "Inspect standard Windows Run-key entries. Publisher and startup impact are shown only when available; this implementation does not estimate either.")
        controls = QHBoxLayout()
        self.startup_status = _label("Reading startup entries…", "muted")
        controls.addWidget(self.startup_status, 1)
        refresh = _button("Refresh", "secondary")
        refresh.clicked.connect(self._request_startup)
        controls.addWidget(refresh)
        layout.addLayout(controls)
        self.startup_table = QTableWidget(0, 5)
        self.startup_table.setHorizontalHeaderLabels(["Application", "Publisher", "Startup location", "Impact", "Status"])
        self.startup_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.startup_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.startup_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.startup_table.itemSelectionChanged.connect(self._update_startup_action_label)
        self.startup_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.startup_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for col in (1, 3, 4):
            self.startup_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.startup_table, 1)
        row = QHBoxLayout()
        inspect_btn = _button("Inspect command", "secondary")
        inspect_btn.clicked.connect(self._inspect_startup)
        row.addWidget(inspect_btn)
        self.startup_toggle = _button("Disable selected…", "secondary")
        self.startup_toggle.clicked.connect(self._toggle_startup_entry)
        row.addWidget(self.startup_toggle)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(_label("Disable moves a Run-key value to a reversible RAM Optimiser backup key. Entries under HKLM may require an administrator account; denied changes are reported and left untouched.", "muted"))

    def _build_history(self):
        _, _, layout = self.pages[6]
        add_section_title(layout, "Performance History", "Local, bounded measurements gathered while RAM Optimiser is running. GPU readings remain empty when no supported NVIDIA NVML sensor is available.")
        controls = QHBoxLayout()
        controls.addWidget(_label("TIME RANGE", "eyebrow"))
        self.history_range = QComboBox()
        for label, seconds in (("Last hour", 3600), ("Last 6 hours", 21600), ("Last 24 hours", 86400),
                               ("Last 7 days", 604800), ("All retained", None)):
            self.history_range.addItem(label, seconds)
        self.history_range.setCurrentIndex(2)
        self.history_range.currentIndexChanged.connect(self._load_history)
        controls.addWidget(self.history_range)
        export = _button("Export CSV report…", "secondary")
        export.clicked.connect(self._export_report)
        controls.addWidget(export)
        controls.addStretch(1)
        layout.addLayout(controls)
        charts = QGridLayout()
        self.history_ram = HistoryChart(color="#42c9b4")
        self.history_cpu = HistoryChart(color="#48b9ff")
        self.history_gpu = HistoryChart(color="#9079ff")
        history_chart_cards = []
        for index, (title, chart) in enumerate((("Memory", self.history_ram), ("CPU", self.history_cpu), ("GPU", self.history_gpu))):
            card, card_layout = panel()
            card_layout.addWidget(_label(title, "cardTitle"))
            card_layout.addWidget(chart)
            charts.addWidget(card, 0, index)
            history_chart_cards.append(card)
        self._register_responsive_grid(charts, history_chart_cards, 3, 1)
        layout.addLayout(charts)
        boost_card, boost_layout = panel()
        boost_layout.addWidget(_label("BOOST RESULTS", "eyebrow"))
        self.history_boost_table = QTableWidget(0, 6)
        self.history_boost_table.setHorizontalHeaderLabels(["Timestamp", "Mode", "Available before", "Available after", "Requests OK / failed", "Duration"])
        self.history_boost_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_boost_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_boost_table.setMaximumHeight(260)
        boost_layout.addWidget(self.history_boost_table)
        layout.addWidget(boost_card)
        sessions_card, sessions_layout = panel()
        sessions_layout.addWidget(_label("GAME SESSIONS", "eyebrow"))
        self.history_session_table = QTableWidget(0, 3)
        self.history_session_table.setHorizontalHeaderLabels(["Started", "Game", "Duration"])
        self.history_session_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_session_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_session_table.setMaximumHeight(230)
        sessions_layout.addWidget(self.history_session_table)
        layout.addWidget(sessions_card)
        layout.addStretch(1)

    def _build_settings(self):
        _, _, layout = self.pages[7]
        add_section_title(layout, "Settings", "Choose how RAM Optimiser monitors and stores local information. Optional behavior is off by default.")
        grid = QGridLayout()
        grid.setSpacing(14)
        monitor_card, monitor_layout = panel()
        monitor_layout.addWidget(_label("MONITORING", "eyebrow"))
        monitor_layout.addWidget(_label("Refresh interval", "muted"))
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(1, 30)
        self.refresh_spin.setSuffix(" seconds")
        self.refresh_spin.setValue(self.settings.refresh_seconds)
        monitor_layout.addWidget(self.refresh_spin)
        monitor_layout.addWidget(_label("Storage drive", "muted"))
        self.drive_combo = QComboBox()
        drives = ["C:/"]
        try:
            import psutil
            drives = list(dict.fromkeys([part.mountpoint for part in psutil.disk_partitions(all=False)])) or drives
        except Exception:
            pass
        self.drive_combo.addItems(drives)
        if self.settings.drive_path in drives:
            self.drive_combo.setCurrentText(self.settings.drive_path)
        monitor_layout.addWidget(self.drive_combo)
        monitor_layout.addWidget(_label("History retention", "muted"))
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 365)
        self.retention_spin.setSuffix(" days")
        self.retention_spin.setValue(self.settings.history_retention_days)
        monitor_layout.addWidget(self.retention_spin)
        grid.addWidget(monitor_card, 0, 0)

        auto_card, auto_layout = panel()
        auto_layout.addWidget(_label("AUTOMATIC BOOST", "eyebrow"))
        self.auto_enabled = QCheckBox("Enable automatic Boost")
        self.auto_enabled.setChecked(self.settings.auto_boost_enabled)
        auto_layout.addWidget(self.auto_enabled)
        auto_layout.addWidget(_label("RAM-pressure threshold", "muted"))
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(50, 99)
        self.threshold_spin.setSuffix("%")
        self.threshold_spin.setValue(self.settings.auto_boost_threshold)
        auto_layout.addWidget(self.threshold_spin)
        auto_layout.addWidget(_label("Cooldown", "muted"))
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(5, 1440)
        self.cooldown_spin.setSuffix(" minutes")
        self.cooldown_spin.setValue(self.settings.auto_boost_cooldown_minutes)
        auto_layout.addWidget(self.cooldown_spin)
        auto_layout.addWidget(_label("Check interval", "muted"))
        self.auto_interval_spin = QSpinBox()
        self.auto_interval_spin.setRange(15, 600)
        self.auto_interval_spin.setSuffix(" seconds")
        self.auto_interval_spin.setValue(self.settings.auto_boost_interval_seconds)
        auto_layout.addWidget(self.auto_interval_spin)
        self.auto_approval = QCheckBox("Ask before each automatic Boost")
        self.auto_approval.setChecked(self.settings.auto_boost_require_approval)
        auto_layout.addWidget(self.auto_approval)
        auto_layout.addWidget(_label("Auto Boost uses One-Click Boost and never closes apps. Disabled by default; Windows may reclaim trimmed pages later.", "muted"))
        grid.addWidget(auto_card, 0, 1)

        prefs, prefs_layout = panel()
        prefs_layout.addWidget(_label("WINDOW AND NOTIFICATIONS", "eyebrow"))
        self.tray_enabled = QCheckBox("Show RAM Optimiser in the system tray")
        self.tray_enabled.setChecked(self.settings.tray_enabled)
        prefs_layout.addWidget(self.tray_enabled)
        self.minimize_tray = QCheckBox("Minimize to tray when closing the window")
        self.minimize_tray.setChecked(self.settings.minimize_to_tray)
        prefs_layout.addWidget(self.minimize_tray)
        self.minimize_during_game = QCheckBox("Hide to tray when a selected game starts")
        self.minimize_during_game.setChecked(self.settings.minimize_during_game)
        prefs_layout.addWidget(self.minimize_during_game)
        self.notifications_enabled = QCheckBox("Allow useful system and Boost notifications")
        self.notifications_enabled.setChecked(self.settings.notifications_enabled)
        prefs_layout.addWidget(self.notifications_enabled)
        self.start_windows = QCheckBox("Start RAM Optimiser when I sign in to Windows")
        self.start_windows.setChecked(self.settings.start_with_windows)
        prefs_layout.addWidget(self.start_windows)
        prefs_layout.addWidget(_label("Sign-in startup is an optional per-user Run-key entry. It does not require administrator access.", "muted"))
        grid.addWidget(prefs, 1, 0)

        appearance, appearance_layout = panel()
        appearance_layout.addWidget(_label("APPEARANCE", "eyebrow"))
        appearance_layout.addWidget(_label("Accent colour", "muted"))
        self.accent_button = _button("Choose accent colour", "secondary")
        self.accent_button.clicked.connect(self._choose_accent)
        appearance_layout.addWidget(self.accent_button)
        appearance_layout.addWidget(_label("Dark navy theme with a restrained, customizable highlight.", "muted"))
        grid.addWidget(appearance, 1, 1)
        layout.addLayout(grid)

        lists_card, lists_layout = panel()
        lists_layout.addWidget(_label("APPLICATION LISTS", "eyebrow"))
        lists_layout.addWidget(_label("One application name per line. Essential Windows processes and RAM Optimiser stay protected regardless of these lists. Eligible names may be considered at a lower memory threshold, but still follow the selected Boost mode's limits.", "muted"))
        lists_row = QHBoxLayout()
        self.protected_edit = QTextEdit("\n".join(self.settings.protected_apps))
        self.protected_edit.setPlaceholderText("Protected apps (for example: browser.exe)")
        self.protected_edit.setMaximumHeight(120)
        self.eligible_edit = QTextEdit("\n".join(self.settings.eligible_apps))
        self.eligible_edit.setPlaceholderText("Eligible apps")
        self.eligible_edit.setMaximumHeight(120)
        self.excluded_edit = QTextEdit("\n".join(self.settings.excluded_apps))
        self.excluded_edit.setPlaceholderText("Excluded apps")
        self.excluded_edit.setMaximumHeight(120)
        for widget in (self.protected_edit, self.eligible_edit, self.excluded_edit):
            lists_row.addWidget(widget, 1)
        lists_layout.addLayout(lists_row)
        layout.addWidget(lists_card)

        about, about_layout = panel()
        about_layout.addWidget(_label("ABOUT RAM OPTIMISER", "eyebrow"))
        about_layout.addWidget(_label(f"RAM Optimiser {__version__} · Local-first Windows monitoring and safe working-set requests. No account, ads, analytics, or required network access. Sensors and some process actions depend on hardware, Windows version, and permissions.", "muted"))
        about_layout.addWidget(_label("Help: see README.md and TROUBLESHOOTING.md in the installation folder. Open-source notices are in THIRD_PARTY_NOTICES.md.", "muted"))
        layout.addWidget(about)
        actions = QHBoxLayout()
        save = _button("Save settings", "primary")
        save.clicked.connect(self._save_settings)
        actions.addWidget(save)
        reset = _button("Reset local history…", "danger")
        reset.clicked.connect(self._clear_history)
        actions.addWidget(reset)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)

    def _wire_ui(self):
        self.stack.currentChanged.connect(self._page_changed)
        self._navigate(0)

    def _navigate(self, index: int):
        self.stack.setCurrentIndex(index)
        self._page_changed(index)

    def _page_changed(self, index: int):
        if index < 0 or index >= len(NAV_ITEMS):
            return
        self._current_page = index
        title = NAV_ITEMS[index][0]
        self.page_title.setText(title)
        subtitles = ["A live view of your computer", "Real readings from supported system sources",
                     "Conservative, measured Windows memory requests", "Track a game without risky system changes",
                     "Inspect selected processes and review actions", "Review and manage supported startup entries",
                     "Measurements and actions recorded locally", "Tune monitoring, safety lists, and preferences"]
        self.page_subtitle.setText(subtitles[index])
        for i, button in enumerate(self.nav_buttons):
            button.setProperty("active", i == index)
            button.style().unpolish(button)
            button.style().polish(button)
        if index == 4:
            self._request_processes()
        elif index == 5:
            self._request_startup()
        elif index in (2, 6):
            self._load_boost_history()
            self._load_history()
        elif index == 3:
            self._load_game_history()

    def _apply_theme(self):
        accent = QColor(self.settings.accent)
        if not accent.isValid():
            accent = QColor("#48b9ff")
        color = accent.name()
        self.setStyleSheet(f"""
            QWidget {{ color: #eaf1f7; font-family: 'Segoe UI'; font-size: 10pt; }}
            QMainWindow, #appRoot, #mainContent {{ background: #080d13; }}
            QScrollArea {{ background: #080d13; border: 0; }}
            #pageContainer {{ background: #080d13; }}
            #sidebar {{ background: #0b1119; border-right: 1px solid #1b2732; }}
            #topbar {{ background: #0b1119; border-bottom: 1px solid #1b2732; }}
            #brandTitle {{ color: #f4f8fb; font-size: 13pt; font-weight: 700; }}
            #brandSub, #eyebrow {{ color: #76879a; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }}
            #topTitle {{ color: #f1f6fa; font-size: 15pt; font-weight: 650; }}
            #heroTitle {{ color: #f2f6fa; font-size: 22pt; font-weight: 650; }}
            #sectionTitle {{ color: #f2f6fa; font-size: 22pt; font-weight: 650; }}
            #cardTitle {{ color: #eaf1f7; font-size: 12pt; font-weight: 620; }}
            #muted {{ color: #8d9bab; }}
            #pill, #statusBadge {{ color: #b6c8d9; background: #111c27; border: 1px solid #223443; border-radius: 12px; padding: 6px 10px; }}
            #statusBadge {{ color: #8de0c5; font-size: 8pt; font-weight: 700; }}
            #panel, #metricTile {{ background: #101720; border: 1px solid #202d39; border-radius: 13px; }}
            #localStatus {{ background: #0f1923; border: 1px solid #1c2b39; border-radius: 12px; }}
            #metricTile {{ border-radius: 10px; }}
            #metricValue {{ color: #eef4f8; font-size: 14pt; font-weight: 650; }}
            QPushButton#navButton {{ text-align: left; padding: 0 12px; color: #91a0ae; background: transparent; border: 0; border-radius: 8px; font-weight: 550; }}
            QPushButton#navButton:hover {{ background: #111c27; color: #e8f4fc; }}
            QPushButton#navButton[active="true"] {{ background: #10273a; color: #e9f7ff; border: 1px solid #1c4663; }}
            QPushButton#primary {{ color: #04121c; background: {color}; border: 1px solid {color}; border-radius: 8px; padding: 8px 14px; font-weight: 700; }}
            QPushButton#primary:hover {{ background: #83d2ff; border-color: #83d2ff; }}
            QPushButton#secondary {{ color: #d9e5ee; background: #17232f; border: 1px solid #2b3c4b; border-radius: 8px; padding: 8px 13px; font-weight: 600; }}
            QPushButton#secondary:hover {{ background: #1c3040; border-color: #42657d; }}
            QPushButton#danger {{ color: #ffdadd; background: #321c24; border: 1px solid #61313d; border-radius: 8px; padding: 8px 13px; font-weight: 600; }}
            QPushButton#danger:hover {{ background: #4a232e; }}
            QLineEdit, QTextEdit, QComboBox, QSpinBox {{ color: #e8f0f6; background: #0c131b; border: 1px solid #263541; border-radius: 7px; padding: 8px; selection-background-color: {color}; }}
            QComboBox QAbstractItemView {{ background: #111a23; selection-background-color: #1a3d55; }}
            QCheckBox {{ spacing: 8px; color: #ced9e2; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; }}
            QCheckBox::indicator:unchecked {{ background: #111a23; border: 1px solid #425365; border-radius: 4px; }}
            QCheckBox::indicator:checked {{ background: {color}; border: 1px solid {color}; border-radius: 4px; }}
            QTableWidget {{ color: #dfe8ef; background: #0e151d; alternate-background-color: #111b24; border: 1px solid #24323f; border-radius: 8px; gridline-color: #202d38; selection-background-color: #173750; selection-color: #f4f9fc; }}
            QHeaderView::section {{ color: #8fa0b1; background: #121c26; border: 0; border-bottom: 1px solid #293845; padding: 9px 8px; font-weight: 650; }}
            QProgressBar {{ background: #18232d; border: 0; border-radius: 2px; }}
            QProgressBar::chunk {{ background: {color}; border-radius: 2px; }}
            QScrollArea {{ background: transparent; }}
            QToolTip {{ color: #eaf1f7; background: #18232d; border: 1px solid #364958; padding: 5px; }}
        """)

    def _run_worker(self, function, success, error=None, *args, **kwargs):
        worker = Worker(function, *args, **kwargs)
        self._worker_refs.append(worker)
        worker.signals.result.connect(success)
        worker.signals.error.connect(error or self._show_error)
        worker.signals.finished.connect(lambda w=worker: self._release_worker(w))
        self.thread_pool.start(worker)

    def _release_worker(self, worker):
        try:
            self._worker_refs.remove(worker)
        except ValueError:
            pass

    def _request_snapshot(self):
        if self._snapshot_busy:
            return
        self._snapshot_busy = True
        self.live_badge.setText("●  SAMPLING")
        self.global_refresh.setEnabled(False)
        self._run_worker(collect_snapshot, self._on_snapshot, self._snapshot_error,
                         self.settings.drive_path)

    def _snapshot_error(self, message):
        self._snapshot_busy = False
        self.global_refresh.setEnabled(True)
        self.live_badge.setText("●  UNAVAILABLE")
        self.live_badge.setStyleSheet("color: #ffb4a8; background: #291c1d; border: 1px solid #583638; border-radius: 12px; padding: 6px 10px;")
        self.home_status.setText(f"System measurements unavailable: {message}")

    def _request_process_names(self):
        if self._process_names_busy or self._closing_wait:
            return
        self._process_names_busy = True
        self._run_worker(collect_process_names, self._on_process_names, self._process_names_error)

    def _process_names_error(self, message):
        self._process_names_busy = False
        self._log_error(f"Process-name scan failed: {message}")

    def _on_process_names(self, result):
        self._process_names_busy = False
        self._process_names = result.get("process_names", [])
        self._detect_game({"process_names": self._process_names})

    def _request_top_processes(self):
        if self._top_processes_busy or self._closing_wait:
            return
        self._top_processes_busy = True
        self._run_worker(collect_top_processes, self._on_top_processes, self._top_processes_error)

    def _top_processes_error(self, message):
        self._top_processes_busy = False
        self.home_top_status.setText(f"Process memory scan unavailable: {message}")
        self._log_error(f"Top-process scan failed: {message}")

    def _on_top_processes(self, result):
        self._top_processes_busy = False
        self._top_processes = result.get("top_processes", [])
        self._render_home_top_processes()
        if self._last_snapshot:
            self._update_game_metrics(self._last_snapshot)

    def _render_home_top_processes(self):
        if not hasattr(self, "home_top_processes"):
            return
        self.home_top_processes.setRowCount(0)
        visible = [item for item in self._top_processes if not item.get("protected")][:5]
        for process in visible:
            row = self.home_top_processes.rowCount()
            self.home_top_processes.insertRow(row)
            for col, value in enumerate((process["name"], process["pid"], format_bytes(process["rss"]))):
                self.home_top_processes.setItem(row, col, QTableWidgetItem(str(value)))
        if visible:
            self.home_top_status.setText(f"Process memory sampled {time.strftime('%H:%M:%S')}.")
        elif self._top_processes_busy:
            self.home_top_status.setText("Scanning current process working sets…")
        else:
            self.home_top_status.setText("No application working-set readings are available.")

    def _on_snapshot(self, data):
        self._snapshot_busy = False
        self.global_refresh.setEnabled(True)
        self._last_snapshot = data
        self.live_badge.setText("●  LIVE")
        self.live_badge.setStyleSheet("")
        self.home_status.setText(f"{data['computer_name']} · {data['windows_version']} · Updated just now")
        self.home_gauges["cpu"].set_value(data.get("cpu_percent"), sub_text="CPU utilization")
        self.home_gauges["gpu"].set_value(data.get("gpu", {}).get("utilization"), sub_text="GPU utilization")
        self.home_gauges["ram"].set_value(data.get("ram_percent"), sub_text="Memory utilization")
        storage = data.get("storage") or {}
        self.home_gauges["storage"].set_value(storage.get("percent"), sub_text=f"{storage.get('path', 'Drive')} used")
        gpu = data.get("gpu") or {}
        self.home_tiles["processor"].set_value(data.get("cpu_name") or "Unavailable")
        self.home_tiles["gpu_name"].set_value(gpu.get("name") or "Unavailable")
        self.home_tiles["memory"].set_value(f"{format_bytes(data.get('ram_used'))} / {format_bytes(data.get('ram_total'))}")
        self.home_tiles["processes"].set_value(str(data.get("process_count", "Unavailable")))
        self.home_tiles["computer"].set_value(data.get("computer_name") or "Unavailable")
        self._render_home_top_processes()
        self._update_monitor_page(data)
        self._update_game_metrics(data)
        try:
            self.history.record_sample(data.get("ram_percent"), data.get("cpu_percent"), gpu.get("utilization"))
        except Exception as exc:
            self._log_error(f"Could not store a history sample: {exc}")
        if self._current_page == 6:
            self._load_history()
        self._check_auto_boost(data)

    def _update_monitor_page(self, data):
        gpu = data.get("gpu") or {}
        storage = data.get("storage") or {}
        values = {
            "cpu": f"{data.get('cpu_percent'):.1f}%" if data.get("cpu_percent") is not None else "Unavailable",
            "cpu_temp": f"{data.get('cpu_temperature'):.0f} °C" if data.get("cpu_temperature") is not None else "Unavailable",
            "ram_total": format_bytes(data.get("ram_total")), "ram_used": format_bytes(data.get("ram_used")),
            "ram_available": format_bytes(data.get("ram_available")),
            "gpu": f"{gpu['utilization']:.1f}%" if gpu.get("utilization") is not None else "Unavailable",
            "gpu_temp": f"{gpu['temperature']:.0f} °C" if gpu.get("temperature") is not None else "Unavailable",
            "vram": f"{format_bytes(gpu.get('vram_used'))} / {format_bytes(gpu.get('vram_total'))}" if gpu.get("vram_total") else "Unavailable",
            "storage": f"{format_bytes(storage.get('used'))} / {format_bytes(storage.get('total'))}" if storage.get("total") else "Unavailable",
            "process_count": str(data.get("process_count", "Unavailable")),
        }
        for key, value in values.items():
            self.monitor_tiles[key].set_value(value)
        try:
            samples = self.history.recent_samples(120)
            stamps = [row[0] for row in samples]
            self.monitor_ram_chart.set_values([row[1] for row in samples], stamps)
            self.monitor_cpu_chart.set_values([row[2] for row in samples], stamps)
        except Exception:
            pass
        self.monitor_details.setText(
            f"Device: {data.get('computer_name', 'Unavailable')}\n"
            f"Operating system: {data.get('windows_version', 'Unavailable')}\n"
            f"Processor: {data.get('cpu_name', 'Unavailable')}\n"
            f"Graphics: {gpu.get('name', 'Unavailable')}\n"
            f"Drive: {storage.get('path', 'Unavailable')} · Free {format_bytes(storage.get('free'))}\n"
            f"CPU temperature: {f'{data.get('cpu_temperature'):.0f} °C' if data.get('cpu_temperature') is not None else 'Unavailable (no supported sensor)'}"
        )

    def _update_game_metrics(self, data):
        gpu = data.get("gpu") or {}
        self.game_metrics["cpu"].set_value(f"{data['cpu_percent']:.1f}%" if data.get("cpu_percent") is not None else "Unavailable")
        self.game_metrics["gpu"].set_value(f"{gpu['utilization']:.1f}%" if gpu.get("utilization") is not None else "Unavailable")
        self.game_metrics["ram"].set_value(f"{data['ram_percent']:.1f}%" if data.get("ram_percent") is not None else "Unavailable")
        self.game_metrics["vram"].set_value(f"{format_bytes(gpu.get('vram_used'))} / {format_bytes(gpu.get('vram_total'))}" if gpu.get("vram_total") else "Unavailable")
        self.game_metrics["temperature"].set_value(f"{gpu['temperature']:.0f} °C" if gpu.get("temperature") is not None else "Unavailable")
        self.game_metrics["cpu_temp"].set_value(f"{data['cpu_temperature']:.0f} °C" if data.get("cpu_temperature") is not None else "Unavailable")
        game_name = Path(self.settings.game_executable).name.lower() if self.settings.game_executable else ""
        protected = {name.strip().lower() for name in self.settings.protected_apps}
        excluded = {name.strip().lower() for name in self.settings.excluded_apps}
        top = [p for p in self._top_processes if not p.get("protected")
               and p.get("name", "").lower() != game_name
               and p.get("name", "").lower() not in protected
               and p.get("name", "").lower() not in excluded][:5]
        if top:
            self.game_background.setText("\n".join(f"{p['name']} · PID {p['pid']} · {format_bytes(p['rss'])}" for p in top))
        else:
            self.game_background.setText("No process memory readings available yet.")

    def _check_auto_boost(self, data):
        if self._closing_wait:
            return
        if not self.settings.auto_boost_enabled:
            self._pressure_notified = False
            return
        pressure = data.get("ram_percent")
        if pressure is None or pressure < self.settings.auto_boost_threshold:
            self._pressure_notified = False
            return
        if not self._pressure_notified:
            self._pressure_notified = True
            self._notify("High memory use", f"Memory use reached {pressure:.0f}%. Windows manages memory automatically; review before trimming.")
        now = time.monotonic()
        if now - self._last_auto_check < self.settings.auto_boost_interval_seconds:
            return
        self._last_auto_check = now
        enough_time = time.monotonic() - self._last_auto_run >= self.settings.auto_boost_cooldown_minutes * 60
        if not enough_time or self._boost_busy:
            return
        self._last_auto_run = time.monotonic()
        if self.settings.auto_boost_require_approval:
            answer = QMessageBox.question(self, "Automatic Boost approval",
                f"Memory use is {pressure:.0f}% (threshold {self.settings.auto_boost_threshold}%). Run the conservative One-Click Boost now? It will request working-set trims and will not close apps.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                self._start_boost("One-Click Boost", automatic=True)
        else:
            self._start_boost("One-Click Boost", automatic=True)

    def _start_boost(self, mode, automatic=False):
        if self._boost_busy:
            return
        if not self._operation_gate.try_enter():
            if not automatic:
                QMessageBox.information(self, "Operation in progress", "Wait for the current process or memory operation to finish before starting another one.")
            return
        if not automatic:
            answer = QMessageBox.question(self, f"Run {mode}?",
                "This requests supported Windows working-set trims for eligible apps. It will not terminate apps. Results depend on Windows and may not increase available memory.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self._operation_gate.leave()
                return
        self._boost_busy = True
        self.boost_progress.setRange(0, 0)
        self.boost_result.setText(f"{mode} is scanning eligible processes and requesting Windows trims…")
        for button in self.boost_buttons.values():
            button.setEnabled(False)
        self._run_worker(run_boost, lambda result: self._boost_complete(result, automatic),
                         lambda error: self._boost_error(error, automatic), mode,
                         self.settings.protected_apps, self.settings.excluded_apps,
                         self.settings.eligible_apps)

    def _boost_complete(self, result, automatic):
        self._boost_busy = False
        self._operation_gate.leave()
        self.boost_progress.setRange(0, 1)
        self.boost_progress.setValue(1)
        for button in self.boost_buttons.values():
            button.setEnabled(True)
        delta = result.get("available_delta")
        delta_text = "Unavailable" if delta is None else f"{delta / (1024 ** 2):+.1f} MiB"
        if result.get("attempted", 0) == 0:
            message = "No processes passed the selected mode's eligibility checks."
        else:
            message = f"Available memory: {format_bytes(result.get('before_available'))} → {format_bytes(result.get('after_available'))} ({delta_text}). Requests accepted: {result.get('succeeded')}/{result.get('attempted')}; failed: {result.get('failed')}. {result.get('duration', 0):.1f}s."
        self.boost_result.setText(message + " This is a system measurement; it is not an amount of memory reclaimed by the operation.")
        try:
            self.history.record_boost(result["mode"], result.get("before_available"), result.get("after_available"),
                                      result.get("attempted", 0), result.get("succeeded", 0), result.get("failed", 0),
                                      result.get("duration", 0), result.get("details", []))
            self._load_boost_history()
        except Exception as exc:
            self._log_error(f"Could not save Boost result: {exc}")
        self._notify("Boost finished", message)

    def _boost_error(self, message, automatic):
        self._boost_busy = False
        self._operation_gate.leave()
        self.boost_progress.setRange(0, 1)
        self.boost_progress.setValue(0)
        for button in self.boost_buttons.values():
            button.setEnabled(True)
        self.boost_result.setText(f"Boost did not complete: {message}")
        self._log_error(f"Boost failed: {message}")
        if automatic:
            self._notify("Automatic Boost failed", message)

    def _request_processes(self):
        if self._process_busy:
            return
        self._process_busy = True
        self.process_status_label.setText("Reading process details from Windows…")
        self._run_worker(list_processes, self._on_processes, self._process_error,
                         self.settings.protected_apps, self.settings.excluded_apps)

    def _process_error(self, message):
        self._process_busy = False
        self.process_status_label.setText(f"Could not read process details: {message}")
        self._log_error(f"Could not read processes: {message}")

    def _on_processes(self, records):
        self._process_busy = False
        self._process_records = records
        self._populate_process_table()

    def _populate_process_table(self):
        if not hasattr(self, "process_table"):
            return
        needle = self.process_search.text().strip().lower()
        table = self.process_table
        table.setSortingEnabled(False)
        table.setRowCount(0)
        visible_count = 0
        for record in self._process_records:
            if needle and needle not in record.name.lower() and needle not in str(record.pid):
                continue
            row = table.rowCount()
            visible_count += 1
            table.insertRow(row)
            vals = [record.name, str(record.pid), format_bytes(record.rss), f"{record.cpu_percent:.1f}%",
                    record.status, "Protected" if record.protected else "Not protected"]
            for col, value in enumerate(vals):
                item = SortableItem(value)
                item.setData(Qt.ItemDataRole.UserRole, record)
                if col == 1:
                    item.setData(Qt.ItemDataRole.UserRole + 1, record.pid)
                elif col == 2:
                    item.setData(Qt.ItemDataRole.UserRole + 1, record.rss)
                elif col == 3:
                    item.setData(Qt.ItemDataRole.UserRole + 1, record.cpu_percent)
                if record.protected:
                    item.setForeground(QColor("#8694a1"))
                table.setItem(row, col, item)
        table.setSortingEnabled(True)
        table.sortItems(2, Qt.SortOrder.DescendingOrder)
        if not self._process_records:
            self.process_status_label.setText("No process details were returned by Windows.")
        elif visible_count == 0:
            self.process_status_label.setText("No processes match this search.")
        else:
            refreshed = time.strftime("%H:%M:%S")
            self.process_status_label.setText(
                f"Showing {visible_count} of {len(self._process_records)} processes · refreshed {refreshed} · other-user and unknown-owner processes are protected.")
        self._update_selected_count()

    def _filter_process_table(self, _text):
        self._populate_process_table()

    def _update_selected_count(self):
        if hasattr(self, "process_table"):
            self.process_count_label.setText(f"{len(self.process_table.selectionModel().selectedRows())} selected")

    def _selected_records(self):
        records = []
        seen = set()
        for index in self.process_table.selectionModel().selectedRows():
            item = self.process_table.item(index.row(), 0)
            record = item.data(Qt.ItemDataRole.UserRole) if item else None
            if isinstance(record, ProcessRecord) and record.pid not in seen:
                seen.add(record.pid)
                records.append(record)
        return records

    def _inspect_selected_row(self, row=None):
        if row is None:
            selected = self._selected_records()
            record = selected[0] if selected else None
        else:
            item = self.process_table.item(row, 0)
            record = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not record:
            QMessageBox.information(self, "Inspect process", "Select one process row first.")
            return
        self._run_worker(inspect_process, lambda info: self._show_process_info(info), self._show_error, record.identity)

    def _show_process_info(self, info):
        QMessageBox.information(self, f"Process: {info['name']}",
            f"Name: {info['name']}\nPID: {info['pid']}\nStatus: {info['status']}\n"
            f"Memory (working set): {format_bytes(info['rss'])}\nVirtual memory: {format_bytes(info['vms'])}\n"
            f"Threads: {info['threads']}\nUser: {info['username']}\nExecutable: {info['executable']}\n"
            f"Command: {info['cmdline']}\n\nThe process is revalidated by PID and start time for every action.")

    def _trim_selected(self):
        records = self._selected_records()
        if not records:
            QMessageBox.information(self, "Trim memory", "Select one or more processes first.")
            return
        eligible = [record for record in records if not record.protected]
        if not eligible:
            QMessageBox.information(self, "Trim memory", "Every selected process is protected.")
            return
        if QMessageBox.question(self, "Trim selected process memory",
                f"Request Windows working-set trims for {len(eligible)} selected process(es)? Apps remain running, but may need to reload data.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        if not self._operation_gate.try_enter():
            QMessageBox.information(self, "Operation in progress", "Wait for the current process or memory operation to finish.")
            return
        self.trim_process_button.setEnabled(False)
        def operation():
            results = []
            for record in eligible:
                ok, message = trim_process(record.identity)
                results.append((record.name, ok, message))
            return results
        def done(results):
            self._operation_gate.leave()
            self.trim_process_button.setEnabled(True)
            summary = "\n".join(f"{'Accepted' if ok else 'Not completed'} · {name}: {message}" for name, ok, message in results)
            QMessageBox.information(self, "Trim results", summary or "No operation was performed.")
        def failed(message):
            self._operation_gate.leave()
            self.trim_process_button.setEnabled(True)
            self._show_error(message)
        self._run_worker(operation, done, failed)

    def _close_selected(self, force=False):
        records = self._selected_records()
        if not records:
            QMessageBox.information(self, "Close process", "Select one or more processes first.")
            return
        eligible = [r for r in records if not r.protected]
        if not eligible:
            QMessageBox.information(self, "Close process", "Every selected process is protected.")
            return
        title = "Force terminate selected processes?" if force else "Ask selected applications to close?"
        body = (f"Force termination will immediately stop {len(eligible)} process(es). Unsaved work can be lost.\n\n"
                if force else f"Send a close request to {len(eligible)} selected process(es). They may prompt you to save.\n\n")
        body += "\n".join(f"{r.name} (PID {r.pid})" for r in eligible[:12])
        if len(eligible) > 12:
            body += f"\n…and {len(eligible) - 12} more"
        if QMessageBox.warning(self, title, body, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                               QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        if not self._operation_gate.try_enter():
            QMessageBox.information(self, "Operation in progress", "Wait for the current process or memory operation to finish.")
            return
        self.close_process_button.setEnabled(False)
        self.force_process_button.setEnabled(False)
        def operation():
            return [(r.name, *close_process(r.identity, force)) for r in eligible]
        def done(results):
            self._operation_gate.leave()
            self.close_process_button.setEnabled(True)
            self.force_process_button.setEnabled(True)
            QMessageBox.information(self, "Process action results", "\n".join(
                f"{'Request sent' if ok else 'Not completed'} · {name}: {message}" for name, ok, message in results))
            self._request_processes()
        def failed(message):
            self._operation_gate.leave()
            self.close_process_button.setEnabled(True)
            self.force_process_button.setEnabled(True)
            self._show_error(message)
        self._run_worker(operation, done, failed)

    def _request_startup(self):
        if self._startup_busy:
            return
        self._startup_busy = True
        self.startup_status.setText("Reading standard Windows Run keys…")
        self._run_worker(startup_entries, self._on_startup_entries, self._startup_error)

    def _startup_error(self, message):
        self._startup_busy = False
        self.startup_status.setText(f"Startup entries unavailable: {message}")

    def _on_startup_entries(self, entries):
        self._startup_busy = False
        table = self.startup_table
        table.setRowCount(0)
        for entry in entries:
            row = table.rowCount()
            table.insertRow(row)
            values = [entry.get("name", "Unknown"), entry.get("publisher", "Unavailable"),
                      entry.get("location", "Unavailable"), entry.get("impact", "Unavailable"),
                      "Enabled" if entry.get("enabled") else "Disabled"]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, entry)
                table.setItem(row, col, item)
        self.startup_status.setText(f"{len(entries)} standard Run-key entries found." if os.name == "nt" else "Startup inspection is available on Windows only.")
        self._update_startup_action_label()

    def _update_startup_action_label(self):
        entry = self._selected_startup_entry() if hasattr(self, "startup_table") else None
        self.startup_toggle.setText("Enable selected…" if entry and not entry.get("enabled", True) else "Disable selected…")

    def _selected_startup_entry(self):
        rows = self.startup_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.startup_table.item(rows[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _inspect_startup(self):
        entry = self._selected_startup_entry()
        if not entry:
            QMessageBox.information(self, "Inspect startup entry", "Select one startup entry first.")
            return
        QMessageBox.information(self, entry["name"], f"Application: {entry['name']}\nCommand: {entry['command']}\nLocation: {entry['location']}\nPublisher: Unavailable\nStartup impact: Unavailable")

    def _toggle_startup_entry(self):
        entry = self._selected_startup_entry()
        if not entry:
            QMessageBox.information(self, "Startup Apps", "Select one startup entry first.")
            return
        enable = not entry.get("enabled", True)
        action = "restore" if enable else "disable"
        if QMessageBox.question(self, f"{action.capitalize()} startup app?",
                f"{action.capitalize()} {entry['name']} in Windows startup? You can reverse this later from RAM Optimiser.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        self.startup_toggle.setEnabled(False)
        def done(result):
            self.startup_toggle.setEnabled(True)
            ok, message = result
            if ok:
                QMessageBox.information(self, "Startup setting updated", message)
            else:
                QMessageBox.warning(self, "Startup setting unchanged", message)
            self._request_startup()
        self._run_worker(set_startup_entry, done, lambda e: (self.startup_toggle.setEnabled(True), self._show_error(e)), entry, enable)

    def _choose_game(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select a game executable", "", "Applications (*.exe);;All files (*.*)")
        if path:
            self.settings.game_executable = path
            if path not in self.settings.game_profiles:
                self.settings.game_profiles.append(path)
                self.game_profile_combo.addItem(Path(path).name, path)
                self.game_profile_combo.setItemData(self.game_profile_combo.count() - 1, path, Qt.ItemDataRole.ToolTipRole)
            self.game_profile_combo.setEnabled(True)
            self.game_profile_combo.setCurrentIndex(self.game_profile_combo.findData(path))
            self.game_path.setText(path)
            self._save_to_disk()
            self._load_game_history()

    def _select_game_profile(self, index):
        if index < 0:
            return
        path = self.game_profile_combo.itemData(index)
        if not path:
            return
        self.settings.game_executable = str(path)
        self.game_path.setText(str(path))
        self._save_to_disk()

    def _remove_game_profile(self):
        index = self.game_profile_combo.currentIndex()
        path = self.game_profile_combo.itemData(index) if index >= 0 else None
        if not path:
            QMessageBox.information(self, "Game profiles", "There is no saved profile to remove.")
            return
        if QMessageBox.question(self, "Remove saved game profile?", f"Remove {Path(path).name} from RAM Optimiser's saved profiles? Existing session history will be kept.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        self.settings.game_profiles = [item for item in self.settings.game_profiles if item != path]
        self.game_profile_combo.removeItem(index)
        self.settings.game_executable = str(self.game_profile_combo.currentData() or "")
        self.game_path.setText(self.settings.game_executable)
        self.game_profile_combo.setEnabled(self.game_profile_combo.count() > 0)
        self._save_to_disk()

    def _detect_game(self, data):
        target = Path(self.settings.game_executable).name.lower() if self.settings.game_executable else ""
        if not target:
            return
        running = target in data.get("process_names", [])
        if running and self._session_id is None:
            self._start_game_session(target)
        elif not running and self._session_id is not None:
            self._end_game_session()

    def _start_game_session(self, game_name):
        self._session_id = self.history.start_session(game_name)
        self._session_started = time.monotonic()
        self._session_elapsed = 0
        self.game_session_label.setText(f"Session active · {game_name}")
        self._notify("Game session started", f"RAM Optimiser detected {game_name}.")
        if self.settings.minimize_during_game and getattr(self, "tray", None) and self.tray.isVisible():
            self.hide()

    def _end_game_session(self):
        if self._session_id is None:
            return
        elapsed = int(time.monotonic() - self._session_started) if self._session_started else 0
        try:
            self.history.end_session(self._session_id, elapsed)
        except Exception as exc:
            self._log_error(f"Could not save game session: {exc}")
        self._session_id = None
        self._session_started = None
        self.game_session_label.setText("No selected game is running.")
        self.game_session_time.setText(self._format_duration(elapsed))
        self._load_game_history()

    def _update_game_session_display(self):
        if self._session_started is not None:
            elapsed = int(time.monotonic() - self._session_started)
            self.game_session_time.setText(self._format_duration(elapsed))

    @staticmethod
    def _format_duration(seconds):
        hours, rem = divmod(max(0, int(seconds)), 3600)
        minutes, secs = divmod(rem, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _load_game_history(self):
        try:
            rows = self.history.recent_sessions(30)
            self._fill_session_table(self.game_sessions, rows)
            if hasattr(self, "history_session_table"):
                self._fill_session_table(self.history_session_table, rows)
        except Exception as exc:
            self._log_error(f"Could not load game history: {exc}")

    def _fill_session_table(self, table, rows):
        table.setRowCount(0)
        for at, ended, game, seconds in rows:
            row = table.rowCount()
            table.insertRow(row)
            duration = seconds or 0
            if not ended and self._session_id is not None and self._session_started is not None:
                duration = int(time.monotonic() - self._session_started)
            vals = [at, game or "Unknown game", self._format_duration(duration)]
            for col, value in enumerate(vals):
                table.setItem(row, col, QTableWidgetItem(str(value)))

    def _load_history(self):
        if not hasattr(self, "history_ram"):
            return
        try:
            seconds = self.history_range.currentData() if hasattr(self, "history_range") else 86400
            limit = 250000 if seconds is None else min(250000, int(seconds / 10) + 5)
            rows = self.history.recent_samples(limit)
            if seconds is not None:
                cutoff = datetime.now(timezone.utc) - timedelta(seconds=seconds)
                rows = [row for row in rows if self._timestamp_is_recent(row[0], cutoff)]
            stamps = [r[0] for r in rows]
            self.history_ram.set_values([r[1] for r in rows], stamps)
            self.history_cpu.set_values([r[2] for r in rows], stamps)
            self.history_gpu.set_values([r[3] for r in rows], stamps)
            monitor_rows = rows[-120:]
            monitor_stamps = [r[0] for r in monitor_rows]
            self.monitor_ram_chart.set_values([r[1] for r in monitor_rows], monitor_stamps)
            self.monitor_cpu_chart.set_values([r[2] for r in monitor_rows], monitor_stamps)
        except Exception as exc:
            self._log_error(f"Could not load performance history: {exc}")

    @staticmethod
    def _timestamp_is_recent(value, cutoff):
        try:
            stamp = datetime.fromisoformat(value)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return stamp >= cutoff
        except (TypeError, ValueError):
            return False

    def _export_report(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export RAM Optimiser report", "RAM-Optimiser-Report.csv", "CSV reports (*.csv)")
        if not path:
            return
        try:
            samples = self.history.recent_samples(250000)
            boosts = self.history.recent_boosts(20000)
            sessions = self.history.recent_sessions(20000)
            with open(path, "w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["record_type", "timestamp", "subject", "ram_percent", "cpu_percent", "gpu_percent",
                                 "available_before_bytes", "available_after_bytes", "attempted", "succeeded", "failed", "duration_seconds"])
                for at, ram, cpu, gpu in samples:
                    writer.writerow(["sample", at, "", ram, cpu, gpu, "", "", "", "", "", ""])
                for at, mode, before, after, attempted, succeeded, failed, duration in boosts:
                    writer.writerow(["boost", at, mode, "", "", "", before, after, attempted, succeeded, failed, duration])
                for started, ended, game, seconds in sessions:
                    writer.writerow(["game_session", started, game or "Unknown game", "", "", "", "", "", "", "", "", seconds or ""])
            QMessageBox.information(self, "Report exported", f"Local history was exported to:\n{path}")
        except (OSError, ValueError) as exc:
            self._show_error(f"The report could not be written: {exc}")

    def _load_boost_history(self):
        try:
            rows = self.history.recent_boosts(30)
        except Exception as exc:
            self._log_error(f"Could not load Boost history: {exc}")
            return
        for table in (getattr(self, "boost_recent", None), getattr(self, "history_boost_table", None)):
            if table is None:
                continue
            table.setRowCount(0)
            for at, mode, before, after, attempted, succeeded, failed, duration in rows:
                row = table.rowCount()
                table.insertRow(row)
                values = [at, mode, format_bytes(before), format_bytes(after),
                          f"{succeeded}/{attempted} accepted · {failed} failed", f"{duration:.1f}s"]
                for col, value in enumerate(values):
                    table.setItem(row, col, QTableWidgetItem(str(value)))

    def _choose_accent(self):
        color = QColorDialog.getColor(QColor(self.settings.accent), self, "Choose accent colour")
        if color.isValid():
            self.settings.accent = color.name()
            self._save_to_disk()
            self._apply_theme()

    def _save_settings(self):
        was_autostart = self.settings.start_with_windows
        self.settings.refresh_seconds = self.refresh_spin.value()
        self.settings.drive_path = self.drive_combo.currentText()
        self.settings.history_retention_days = self.retention_spin.value()
        self.settings.auto_boost_enabled = self.auto_enabled.isChecked()
        self.settings.auto_boost_threshold = self.threshold_spin.value()
        self.settings.auto_boost_cooldown_minutes = self.cooldown_spin.value()
        self.settings.auto_boost_interval_seconds = self.auto_interval_spin.value()
        self.settings.auto_boost_require_approval = self.auto_approval.isChecked()
        self.settings.tray_enabled = self.tray_enabled.isChecked()
        self.settings.minimize_to_tray = self.minimize_tray.isChecked()
        self.settings.minimize_during_game = self.minimize_during_game.isChecked()
        self.settings.notifications_enabled = self.notifications_enabled.isChecked()
        self.settings.start_with_windows = self.start_windows.isChecked()
        self.settings.protected_apps = self._clean_names(self.protected_edit.toPlainText())
        self.settings.eligible_apps = self._clean_names(self.eligible_edit.toPlainText())
        self.settings.excluded_apps = self._clean_names(self.excluded_edit.toPlainText())
        self._save_to_disk()
        self.history.retention_days = self.settings.history_retention_days
        self._monitor_timer.setInterval(self.settings.refresh_seconds * 1000)
        if self.settings.start_with_windows != was_autostart:
            ok, message = set_run_at_logon(self.settings.start_with_windows)
            if not ok:
                self.settings.start_with_windows = was_autostart
                self.start_windows.setChecked(was_autostart)
                self._save_to_disk()
                QMessageBox.warning(self, "Windows startup preference unchanged", message)
        self._apply_theme()
        self._init_tray()
        QMessageBox.information(self, "Settings saved", "Your preferences were saved locally.")

    @staticmethod
    def _clean_names(text):
        return list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))

    def _save_to_disk(self):
        try:
            self.settings_store.save(self.settings)
        except OSError as exc:
            QMessageBox.warning(self, "Settings could not be saved", str(exc))

    def _clear_history(self):
        if QMessageBox.warning(self, "Reset local history?", "This permanently clears stored measurements, Boost results, and game sessions on this PC.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.history.clear()
            self._load_history()
            self._load_boost_history()
            self._load_game_history()
            QMessageBox.information(self, "History cleared", "Local performance history was cleared.")
        except Exception as exc:
            self._show_error(str(exc))

    def _init_tray(self):
        if not self.settings.tray_enabled or not QSystemTrayIcon.isSystemTrayAvailable():
            if hasattr(self, "tray"):
                self.tray.hide()
            return
        if not hasattr(self, "tray"):
            self.tray = QSystemTrayIcon(self)
            icon_path = Path(__file__).resolve().parent / "assets" / "ram_optimiser.svg"
            if icon_path.exists():
                self.tray.setIcon(QIcon(str(icon_path)))
            else:
                self.tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
            menu = QMenu()
            open_action = QAction("Open RAM Optimiser", self)
            open_action.triggered.connect(self._show_window)
            menu.addAction(open_action)
            status = QAction("Show current status", self)
            status.triggered.connect(self._tray_status)
            menu.addAction(status)
            boost = QAction("Run One-Click Boost…", self)
            boost.triggered.connect(lambda: (self._show_window(), self._navigate(2), self._start_boost("One-Click Boost")))
            menu.addAction(boost)
            menu.addSeparator()
            exit_action = QAction("Exit RAM Optimiser", self)
            exit_action.triggered.connect(self._exit_application)
            menu.addAction(exit_action)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self):
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_status(self):
        data = self._last_snapshot or {}
        if data:
            message = f"Memory {data.get('ram_percent', 0):.0f}% · CPU {data.get('cpu_percent', 0):.0f}% · {data.get('process_count', 0)} processes"
        else:
            message = "System measurements are not available yet."
        self._notify("RAM Optimiser status", message)

    def _notify(self, title, message):
        if getattr(self, "tray", None) and self.settings.notifications_enabled and self.tray.isVisible():
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4500)

    def _show_error(self, message):
        self._log_error(message)
        QMessageBox.warning(self, "RAM Optimiser", str(message))

    def _log_error(self, message):
        try:
            log_path = self.settings_store.path.parent / "ram-optimiser.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
        except OSError:
            pass

    def _exit_application(self):
        self._force_exit = True
        self.close()

    def closeEvent(self, event):
        if (not self._force_exit and self.settings.minimize_to_tray and self.settings.tray_enabled
                and getattr(self, "tray", None) and self.tray.isVisible()):
            self.hide()
            self._notify("RAM Optimiser is running", "Monitoring continues in the system tray.")
            event.ignore()
            return
        self._shutdown_workers()
        if self.thread_pool.activeThreadCount() > 0 or self._worker_refs:
            self._closing_wait = True
            self.hide()
            event.ignore()
            QTimer.singleShot(100, self._poll_close)
            return
        if self._session_id is not None:
            self._end_game_session()
        if getattr(self, "tray", None):
            self.tray.hide()
        event.accept()

    def _poll_close(self):
        if self.thread_pool.activeThreadCount() > 0 or self._worker_refs:
            QTimer.singleShot(100, self._poll_close)
            return
        self._closing_wait = False
        self._force_exit = True
        self.close()

    def _shutdown_workers(self):
        if hasattr(self, "_monitor_timer"):
            self._monitor_timer.stop()
        if hasattr(self, "_process_names_timer"):
            self._process_names_timer.stop()
        if hasattr(self, "_top_process_timer"):
            self._top_process_timer.stop()
        if hasattr(self, "_game_timer"):
            self._game_timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "sidebar"):
            return
        compact = self.width() < 1340
        if getattr(self, "_compact_sidebar", None) != compact:
            self._compact_sidebar = compact
            self.sidebar.setFixedWidth(74 if compact else 226)
            self.sidebar_layout.setContentsMargins(8 if compact else 16, 18, 8 if compact else 14, 18)
            self.sidebar_layout.setSpacing(6)
            self.brand_title_label.setVisible(not compact)
            self.brand_sub_label.setVisible(not compact)
            self.nav_caption_label.setVisible(not compact)
            self.local_status_box.setVisible(not compact)
            self.version_label.setVisible(not compact)
            for index, button in enumerate(self.nav_buttons):
                button.setText("" if compact else NAV_ITEMS[index][0])
                button.setToolTip(NAV_ITEMS[index][0] if compact else "")
                button.setStyleSheet("text-align: center; padding-left: 0; padding-right: 0;" if compact else "")
        narrow_content = self.width() < 1190
        updated = []
        for layout, widgets, wide_columns, narrow_columns, current_columns in self._responsive_layouts:
            columns = narrow_columns if narrow_content else wide_columns
            if columns != current_columns:
                for widget in widgets:
                    layout.removeWidget(widget)
                for index, widget in enumerate(widgets):
                    layout.addWidget(widget, index // columns, index % columns)
            updated.append((layout, widgets, wide_columns, narrow_columns, columns))
        self._responsive_layouts = updated

