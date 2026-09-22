#!/usr/bin/env python3
"""DLYSO desktop workspace. Launch with ``python dlyso_ui.py``."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPainterPath, QPalette, QPen, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableView,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from dlyso_engine import PipelineRun
from dlyso_runtime import VERSION, atomic_json, guard_input
from dlyso_workflow import APP_DIR, MODALITIES, PROJECT_RE, build_commands, build_workflow  # noqa: F401

INK = "#172d36"
TEAL = "#167868"
MUTED = "#65777c"
DESCRIPTIONS = {
    "SEDplot": ("Spectral energy distribution", "Broadband photometry from VizieR", "No account needed"),
    "SEDrplot": ("Dust-aware SED", "SED shape with a CSFD dust background", "Requires local CSFD maps"),
    "AllWISE": ("AllWISE images", "30 arcsec AllWISE colour cutout", "No account needed"),
    "DTDM": ("ZTF light curves", "ZTF light curves as time–magnitude maps", "Public ZTF archive"),
}
STYLE = """
QWidget { color: #172d36; font-family: 'Avenir Next', 'Segoe UI', sans-serif; font-size: 13px; }
QMainWindow, QWidget#canvas { background: #f4f5f1; }
QWidget#sidebar { background: #172d36; }
QLabel#brand { color: #f5f6f0; font-size: 27px; font-weight: 600; letter-spacing: 3px; }
QLabel#sideMuted { color: #a4bbb9; font-size: 11px; }
QPushButton#nav { text-align: left; color: #bed0ce; border: 0; background: transparent; padding: 13px 15px; border-radius: 6px; }
QPushButton#nav:checked { background: #2b454b; color: #ffffff; }
QPushButton#nav:hover { background: #243d44; }
QLabel#eyebrow { color: #167868; font-size: 10px; font-weight: 600; letter-spacing: 2px; }
QLabel#title { font-size: 29px; font-weight: 600; }
QLabel#section { font-size: 17px; font-weight: 600; }
QLabel#muted { color: #65777c; font-size: 12px; }
QLabel#metric { font-size: 28px; font-weight: 600; }
QLabel#notice { background: #e9efea; color: #315d50; border-radius: 6px; padding: 12px; }
QLabel#error { background: #f9eae3; color: #90412e; border-radius: 6px; padding: 12px; }
QFrame#panel { background: #ffffff; border: 1px solid #dce2dc; border-radius: 9px; }
QFrame#modality { background: #ffffff; border: 1px solid #dce2dc; border-radius: 8px; }
QFrame#modality[selected="true"] { background: #f1f7f3; border: 1px solid #358773; }
QLineEdit, QSpinBox, QComboBox { background: #ffffff; border: 1px solid #cad4ce; border-radius: 5px; padding: 9px; selection-background-color: #167868; selection-color: #ffffff; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid #167868; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { color: #596b65; background: #f0f2ee; }
QComboBox QAbstractItemView { color: #172d36; background: #ffffff; selection-background-color: #167868; selection-color: #ffffff; }
QPushButton { background: #ffffff; border: 1px solid #ccd5ce; border-radius: 5px; padding: 9px 14px; font-weight: 500; }
QPushButton:hover { background: #edf3ee; border-color: #97afa0; }
QPushButton:disabled { color: #596b65; background: #eff1ed; border-color: #e1e6df; }
QPushButton#primary { background: #167868; color: white; border: 1px solid #167868; padding: 12px 20px; }
QPushButton#primary:hover { background: #105f52; }
QPushButton#primary:disabled { background: #b9cec5; border-color: #b9cec5; color: #344e44; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #aebfb4; border-radius: 4px; background: white; }
QCheckBox::indicator:checked { background: #167868; border: 3px solid #83b7a1; }
QProgressBar { border: none; background: #e8ede6; border-radius: 3px; max-height: 6px; min-height: 6px; }
QProgressBar::chunk { background: #398775; border-radius: 3px; }
QPlainTextEdit { background: #1b3039; color: #d4e1d8; border: none; border-radius: 6px; padding: 12px; font-family: 'Menlo', 'Consolas', monospace; font-size: 11px; }
QTableView { background: white; alternate-background-color: #f7f9f5; border: none; selection-background-color: #e0eee7; selection-color: #172d36; gridline-color: #edf0e9; }
QHeaderView::section { background: #f1f4ef; color: #64766d; border: none; border-bottom: 1px solid #dce2dc; padding: 10px 7px; font-size: 11px; font-weight: 600; }
QTableView::item { padding: 7px; border-bottom: 1px solid #edf0e9; }
QScrollArea { border: none; background: transparent; }
QTextBrowser { color: #172d36; background: #f4f5f1; border: none; selection-background-color: #167868; selection-color: #ffffff; }
QTableCornerButton::section { background: #f1f4ef; border: none; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #bccbc0; border-radius: 4px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #172d36; color: white; border: none; padding: 6px; }
"""


def gui_palette():
    """Keep every Qt surface consistent with the light application stylesheet."""
    palette = QPalette()
    colors = {
        "Window": "#f4f5f1", "WindowText": INK,
        "Base": "#ffffff", "AlternateBase": "#f7f9f5", "Text": INK,
        "Button": "#ffffff", "ButtonText": INK,
        "Highlight": TEAL, "HighlightedText": "#ffffff",
        "PlaceholderText": "#596b65", "Link": "#126c5d", "LinkVisited": "#694d82",
        "ToolTipBase": INK, "ToolTipText": "#ffffff",
        "Light": "#ffffff", "Midlight": "#e8ede6", "Mid": "#aebfb4",
        "Dark": "#65777c", "Shadow": "#172d36", "BrightText": "#ffffff",
    }
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
        for role, color in colors.items():
            palette.setColor(group, getattr(QPalette.ColorRole, role), QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#596b65"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#f0f2ee"))
    return palette


def label(text, name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName("primary")
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(callback)
    return widget


def panel():
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(24, 22, 24, 22)
    layout.setSpacing(14)
    return frame, layout


class SignalSketch(QWidget):
    """Small line illustrations; these are modality symbols, never data plots."""

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(72, 48)
        self.setAccessibleName(f"{kind} modality illustration")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#c9d9d0"), 1))
        for y in (12, 24, 36):
            painter.drawLine(0, y, 72, y)
        painter.setPen(QPen(QColor(TEAL), 1.7))
        if self.kind in {"SEDplot", "SEDrplot"}:
            points = [(1, 37), (12, 31), (23, 13), (33, 10), (43, 20), (55, 27), (70, 30)]
            path = QPainterPath()
            path.moveTo(*points[0])
            for point in points[1:]:
                path.lineTo(*point)
            painter.drawPath(path)
            for x, y in points[1:-1]:
                painter.drawEllipse(x - 2, y - 2, 4, 4)
            if self.kind == "SEDrplot":
                painter.setPen(QPen(QColor("#ba795c"), 2))
                painter.drawLine(0, 44, 72, 44)
        elif self.kind == "AllWISE":
            painter.drawEllipse(22, 8, 29, 29)
            painter.drawEllipse(30, 16, 13, 13)
            painter.drawLine(36, 1, 36, 12)
            painter.drawLine(36, 34, 36, 45)
        else:
            for x, y in [(4, 29), (11, 17), (20, 26), (27, 9), (37, 33), (45, 21), (54, 31), (65, 13)]:
                painter.drawLine(x, y - 4, x, y + 4)
                painter.drawEllipse(x - 2, y - 2, 4, 4)
        painter.end()


class ModalityCard(QFrame):
    changed = Signal()

    def __init__(self, key, selected):
        super().__init__()
        self.setObjectName("modality")
        self.setMinimumHeight(138)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setProperty("selected", selected)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        top = QHBoxLayout()
        self.check = QCheckBox()
        self.check.setAccessibleName(DESCRIPTIONS[key][0])
        self.check.setChecked(selected)
        top.addWidget(self.check)
        title = label(DESCRIPTIONS[key][0], wrap=True)
        title.setFont(QFont("Avenir Next", 12, QFont.Weight.DemiBold))
        title.mousePressEvent = lambda event: self.check.toggle()
        top.addWidget(title, 1)
        layout.addLayout(top)
        middle = QHBoxLayout()
        middle.addWidget(label(DESCRIPTIONS[key][1], "muted", True), 1)
        middle.addWidget(SignalSketch(key))
        layout.addLayout(middle)
        layout.addWidget(label(DESCRIPTIONS[key][2], "muted", True))
        self.check.toggled.connect(self._changed)

    def _changed(self, value):
        self.setProperty("selected", value)
        self.style().unpolish(self)
        self.style().polish(self)
        self.changed.emit()


class EventBridge(QObject):
    event = Signal(str, object)


class CatalogueModel(QAbstractTableModel):
    def __init__(self, frame=pd.DataFrame(), parent=None):
        super().__init__(parent)
        self.frame = frame

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.frame)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.frame.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        value = self.frame.iloc[index.row(), index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            if pd.isna(value):
                return "—"
            if isinstance(value, (float, np.floating)):
                return (
                    f"{value:.6f}" if self.frame.columns[index.column()] in {"RA / deg", "Dec / deg"} else f"{value:g}"
                )
            return str(value)
        if role == Qt.ItemDataRole.ForegroundRole and str(value) == "Not evaluated":
            return QColor("#9a674f")
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        count = len(self.frame.columns) if orientation == Qt.Orientation.Horizontal else len(self.frame)
        if not 0 <= section < count:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return str(self.frame.columns[section]) if orientation == Qt.Orientation.Horizontal else str(section + 1)

    def sort(self, column, order):
        if not 0 <= column < len(self.frame.columns):
            return
        self.layoutAboutToBeChanged.emit()
        persistent = self.persistentIndexList()
        identities = [(self.frame.index[index.row()], index.column()) for index in persistent]
        self.frame = self.frame.sort_values(
            self.frame.columns[column],
            ascending=order == Qt.SortOrder.AscendingOrder,
            na_position="last",
            kind="stable",
        )
        self.changePersistentIndexList(
            persistent, [self.index(self.frame.index.get_loc(key), col) for key, col in identities]
        )
        self.layoutChanged.emit()


class DlysoApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DLYSO")
        self.resize(1370, 920)
        self.setMinimumSize(1120, 760)
        self.setPalette(gui_palette())
        self.setStyleSheet(STYLE)
        self.worker = None
        self.worker_thread = None
        self.runroot = None
        self.results = pd.DataFrame()
        self.preview_cache = {}
        self.bridge = EventBridge(self)
        self.bridge.event.connect(self._event)
        self.setAcceptDrops(True)
        self._build()
        self._selection_changed()

    def _build(self):
        root = QWidget()
        root.setObjectName("canvas")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 33, 22, 25)
        side.setSpacing(8)
        side.addWidget(label("DLYSO", "brand"))
        side.addWidget(label("YOUNG STELLAR OBJECTS", "sideMuted"))
        side.addSpacing(48)
        self.nav = []
        for i, title in enumerate(("Project", "Activity", "Results", "Documentation")):
            nav = button(title, lambda checked=False, index=i: self._navigate(index))
            nav.setObjectName("nav")
            nav.setCheckable(True)
            side.addWidget(nav)
            self.nav.append(nav)
        side.addStretch()
        side.addWidget(label("Files are saved locally.\nDownloads use archive services.", "sideMuted", True))
        side.addSpacing(16)
        self.project_tag = label("No project open", "sideMuted", True)
        side.addWidget(self.project_tag)
        side.addWidget(label(f"v{VERSION}", "sideMuted"))
        layout.addWidget(sidebar)
        content = QVBoxLayout()
        content.setContentsMargins(34, 30, 34, 22)
        content.setSpacing(22)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(5)
        self.page_title = label("Project", "title")
        titles.addWidget(self.page_title)
        header.addLayout(titles, 1)
        self.open_button = button("Open project…", self._open_project)
        header.addWidget(self.open_button)
        content.addLayout(header)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._project_page())
        self.pages.addWidget(self._activity_page())
        self.pages.addWidget(self._results_page())
        self.pages.addWidget(self._guide_page())
        content.addWidget(self.pages, 1)
        self.footer = label("Ready  ·  Start with a CSV of ICRS coordinates in degrees.", "muted")
        content.addWidget(self.footer)
        layout.addLayout(content, 1)
        self._navigate(0)

    def _navigate(self, index):
        headings = ("Project", "Activity", "Results", "Documentation")
        self.pages.setCurrentIndex(index)
        for i, nav in enumerate(self.nav):
            nav.setChecked(i == index)
        self.page_title.setText(headings[index])

    def _project_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        widget = QWidget()
        widget.setObjectName("canvas")
        scroll.setWidget(widget)
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(18)
        self.setup = QWidget()
        columns = QHBoxLayout(self.setup)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(20)
        left, fields = panel()
        left.setMinimumWidth(330)
        fields.addWidget(label("Catalogue and output folder", "section"))
        fields.addWidget(label("Input catalogue", "muted"))
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Drop a CSV here or browse…")
        self.input_edit.setAccessibleName("Input catalogue CSV")
        row = QHBoxLayout()
        row.addWidget(self.input_edit, 1)
        row.addWidget(button("Browse", self._browse_input))
        fields.addLayout(row)
        self.input_note = label("Accepted coordinates: ra / dec, RAJ2000 / DEJ2000, or _RA / _DE.", "muted", True)
        fields.addWidget(self.input_note)
        self.catalogue_preview = QTableView()
        self.catalogue_preview.setModel(CatalogueModel())
        self.catalogue_preview.setMaximumHeight(124)
        self.catalogue_preview.setMinimumHeight(98)
        self.catalogue_preview.verticalHeader().hide()
        self.catalogue_preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        fields.addWidget(self.catalogue_preview)
        self.input_timer = QTimer(self)
        self.input_timer.setSingleShot(True)
        self.input_timer.timeout.connect(self._preview_input)
        self.input_edit.textChanged.connect(lambda: self.input_timer.start(350))
        fields.addSpacing(4)
        fields.addWidget(label("Project name", "muted"))
        self.name_edit = QLineEdit("first-catalogue")
        self.name_edit.setAccessibleName("Project name")
        fields.addWidget(self.name_edit)
        fields.addWidget(label("Save projects in", "muted"))
        row = QHBoxLayout()
        self.output_edit = QLineEdit(str(Path.home() / "DLYSO Projects"))
        self.output_edit.setAccessibleName("Projects folder")
        row.addWidget(self.output_edit, 1)
        row.addWidget(button("Browse", self._browse_output))
        fields.addLayout(row)
        fields.addWidget(
            label("Each project keeps its inputs, images, model outputs, and run history together.", "muted", True)
        )
        fields.addStretch()
        fields.addWidget(button("Use the example catalogue", self._example))
        columns.addWidget(left, 4)
        right = QWidget()
        choices = QVBoxLayout(right)
        choices.setContentsMargins(0, 0, 0, 0)
        choices.setSpacing(12)
        choices.addWidget(label("Data channels", "section"))
        choices.addWidget(label("Select the data to download and classify.", "muted", True))
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.cards = {}
        for i, key in enumerate(MODALITIES):
            card = ModalityCard(key, key == "SEDplot")
            card.changed.connect(self._selection_changed)
            self.cards[key] = card
            grid.addWidget(card, i // 2, i % 2)
        choices.addLayout(grid)
        options, controls = panel()
        controls.setContentsMargins(18, 16, 18, 16)
        self.classify_check = QCheckBox("Run classifiers and build the results table")
        self.classify_check.setChecked(True)
        self.classify_check.toggled.connect(self._selection_changed)
        controls.addWidget(self.classify_check)
        parameters = QHBoxLayout()
        parameters.addWidget(label("Download workers", "muted"))
        self.workers = QSpinBox()
        self.workers.setRange(1, 32)
        self.workers.setValue(4)
        self.workers.setAccessibleName("Download workers per channel")
        parameters.addWidget(self.workers)
        parameters.addStretch()
        parameters.addWidget(label("Inference batch", "muted"))
        self.batch = QSpinBox()
        self.batch.setRange(1, 512)
        self.batch.setValue(16)
        self.batch.setAccessibleName("Inference batch size")
        parameters.addWidget(self.batch)
        controls.addLayout(parameters)
        choices.addWidget(options)
        choices.addStretch()
        columns.addWidget(right, 6)
        outer.addWidget(self.setup, 1)
        self.notice = label("", "notice", True)
        outer.addWidget(self.notice)
        bottom = QHBoxLayout()
        self.summary = label("", "muted")
        bottom.addWidget(self.summary, 1)
        self.run_button = button("Start project  →", self._start, True)
        bottom.addWidget(self.run_button)
        outer.addLayout(bottom)
        return scroll

    def _selection_changed(self):
        selected = self._selected()
        classify = self.classify_check.isChecked()
        self.batch.setEnabled(classify)
        self.summary.setText(
            f"{len(selected)} data channel{'s' if len(selected) != 1 else ''}  ·  "
            + (
                f"{12 * len(selected)} model predictions per eligible source"
                if classify
                else "Acquisition & image generation only"
            )
        )
        self.notice.setText(
            "CSFD maps must be installed before running the dust-aware channel. See Documentation → Installation."
            if "SEDrplot" in selected
            else "Sources without usable data are marked ‘not evaluated’."
        )

    def _selected(self):
        return [key for key, card in self.cards.items() if card.check.isChecked()]

    def _activity_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.activity_message = label("No run yet. Configure a catalogue in Project to begin.", "notice", True)
        layout.addWidget(self.activity_message)
        self.stages, stage_layout = panel()
        stage_layout.addWidget(label("Progress", "section"))
        self.stage_rows = QVBoxLayout()
        stage_layout.addLayout(self.stage_rows)
        layout.addWidget(self.stages)
        row = QHBoxLayout()
        row.addWidget(label("Activity log", "section"), 1)
        row.addWidget(button("Save log…", self._save_log))
        self.cancel_button = button("Stop run", self._cancel)
        self.cancel_button.setEnabled(False)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setPlaceholderText("Download and inference messages will appear here.")
        layout.addWidget(self.log, 1)
        self.result_button = button("View results", lambda: self._navigate(2), True)
        self.result_button.setEnabled(False)
        layout.addWidget(self.result_button, 0, Qt.AlignmentFlag.AlignRight)
        return page

    def _results_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)
        metrics = QHBoxLayout()
        self.metrics = {}
        for key, title in [
            ("sources", "CATALOGUE SOURCES"),
            ("evaluated", "WITH PREDICTIONS"),
            ("missing", "NOT EVALUATED"),
        ]:
            card, body = panel()
            body.setContentsMargins(20, 15, 20, 15)
            body.addWidget(label(title, "muted"))
            value = label("—", "metric")
            body.addWidget(value)
            self.metrics[key] = value
            metrics.addWidget(card)
        outer.addLayout(metrics)
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a source by ID or coordinates…")
        self.search.setAccessibleName("Search results")
        self.search.textChanged.connect(self._filter_results)
        toolbar.addWidget(self.search, 1)
        self.result_modality = QComboBox()
        for key, text in MODALITIES.items():
            self.result_modality.addItem(text, key)
        self.result_modality.currentIndexChanged.connect(self._filter_results)
        toolbar.addWidget(self.result_modality)
        self.export_button = button("Export CSV…", self._export_results)
        self.export_button.setEnabled(False)
        toolbar.addWidget(self.export_button)
        outer.addLayout(toolbar)
        self.results_note = label("Results appear as each channel finishes.", "notice", True)
        outer.addWidget(self.results_note)
        body = QHBoxLayout()
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().hide()
        self.table.setModel(CatalogueModel())
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        body.addWidget(self.table, 1)
        detail, details = panel()
        detail.setFixedWidth(280)
        details.setContentsMargins(18, 18, 18, 18)
        self.source_title = label("Source detail", "section", True)
        details.addWidget(self.source_title)
        self.image = label("Select a source to inspect\nits image and model scores.", "muted", True)
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setFixedHeight(200)
        details.addWidget(self.image)
        self.scores = QTextBrowser()
        self.scores.setMinimumHeight(120)
        details.addWidget(self.scores, 1)
        body.addWidget(detail)
        outer.addLayout(body, 1)
        outer.addWidget(
            label(
                "Votes count models above their individual thresholds. Agreement is not a calibrated probability.",
                "muted",
                True,
            )
        )
        return page

    def _guide_page(self):
        page, layout = panel()
        self.guide = QTextBrowser()
        self.guide.setOpenExternalLinks(True)
        guide = APP_DIR / "dlyso_assets/USER_GUIDE.md"
        self.guide.setSearchPaths([str(guide.parent)])
        self.guide.setSource(QUrl.fromLocalFile(str(guide)), QTextDocument.ResourceType.MarkdownResource)
        layout.addWidget(button("Back", self.guide.backward), 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.guide)
        layout.addWidget(button("Open full reference in browser", self._open_docs), 0, Qt.AlignmentFlag.AlignLeft)
        return page

    def _open_docs(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(APP_DIR / "dlyso_assets/reference.html")))

    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select coordinate catalogue", "", "CSV catalogues (*.csv)")
        if path:
            self.input_edit.setText(path)

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Choose projects folder", self.output_edit.text())
        if path:
            self.output_edit.setText(path)

    def _example(self):
        self.input_edit.setText(str(APP_DIR / "dlyso_assets/coordinates.csv"))
        self.name_edit.setText("example-catalogue")

    def _preview_input(self):
        path = Path(self.input_edit.text()).expanduser()
        try:
            frame = pd.read_csv(path, nrows=4)
            self.catalogue_preview.setModel(CatalogueModel(frame.iloc[:3, :4]))
            self.input_note.setText(
                f"{path.name}  ·  Preview of the first {min(3, len(frame))} rows. Full validation runs before downloads."
            )
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            self.catalogue_preview.setModel(CatalogueModel())
            self.input_note.setText(
                "Choose a readable CSV with coordinates in degrees."
                if not path.is_file()
                else f"Cannot read this CSV: {type(exc).__name__}"
            )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and event.mimeData().urls()[0].toLocalFile().lower().endswith(".csv"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.worker_thread or not self.worker_thread.is_alive():
            self.input_edit.setText(event.mimeData().urls()[0].toLocalFile())
            self._navigate(0)
            event.acceptProposedAction()

    def _error(self, message):
        self.footer.setText(message)
        QMessageBox.warning(self, "DLYSO", message)

    def _start(self):
        selected = self._selected()
        source = Path(self.input_edit.text()).expanduser()
        name = self.name_edit.text().strip()
        if not source.is_file():
            return self._error("Choose an existing input CSV.")
        if not PROJECT_RE.fullmatch(name):
            return self._error("Use 1–80 letters, digits, dots, underscores or hyphens; start with a letter or digit.")
        if not selected:
            return self._error("Select at least one data channel.")
        runroot = (Path(self.output_edit.text()).expanduser() / name).resolve()
        try:
            guard_input(runroot, source)
            if runroot.exists() and any(runroot.iterdir()):
                if not (runroot / "run_manifest.json").exists():
                    return self._error(
                        "This folder contains files but has no DLYSO fingerprint. Choose a new project name."
                    )
                if (
                    QMessageBox.question(
                        self, "Resume project", "Reuse completed artifacts and retry missing data in this project?"
                    )
                    != QMessageBox.StandardButton.Yes
                ):
                    return
            runroot.mkdir(parents=True, exist_ok=True)
            atomic_json(
                runroot / "project.json",
                {
                    "project": name,
                    "input_csv": str(source.resolve()),
                    "runroot": str(runroot),
                    "modalities": selected,
                    "classification": self.classify_check.isChecked(),
                    "workers": self.workers.value(),
                    "batch_size": self.batch.value(),
                    "version": VERSION,
                },
            )
        except (OSError, ValueError) as exc:
            return self._error(str(exc))
        self.runroot = runroot
        self.project_tag.setText(name)
        workflow = build_workflow(
            source.resolve(),
            runroot,
            selected,
            self.workers.value(),
            self.batch.value(),
            self.classify_check.isChecked(),
        )
        self._build_stages(workflow)
        env = os.environ.copy()
        self.worker = PipelineRun(workflow, runroot, env, self.bridge.event.emit)
        self.worker_thread = threading.Thread(target=self.worker.run, daemon=True)
        self.setup.setEnabled(False)
        self.open_button.setEnabled(False)
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.result_button.setEnabled(False)
        self.log.clear()
        self.activity_message.setText("Running · independent data channels are processed concurrently.")
        self._navigate(1)
        self.worker_thread.start()

    def _build_stages(self, workflow):
        while self.stage_rows.count():
            item = self.stage_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.stage_widgets = {}
        self.channel_steps = workflow.channel_stages()
        self.task_states = {}
        for modality in self.channel_steps:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 3, 0, 3)
            layout.addWidget(label(MODALITIES[modality]), 1)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setFixedWidth(140)
            bar.setValue(0)
            layout.addWidget(bar)
            state = label("Waiting", "muted")
            state.setFixedWidth(110)
            state.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(state)
            self.stage_rows.addWidget(row)
            self.stage_widgets[modality] = (bar, state)

    def _refresh_channel_progress(self):
        for modality, steps in self.channel_steps.items():
            statuses = [self.task_states.get(title, "waiting") for title in steps]
            bar, label_widget = self.stage_widgets[modality]
            bar.setRange(0, len(steps))
            bar.setValue(statuses.count("complete"))
            if "failed" in statuses:
                text = "Failed"
            elif "blocked" in statuses:
                text = "Blocked"
            elif "cancelled" in statuses:
                text = "Stopped"
            elif all(status == "complete" for status in statuses):
                text = "Complete"
            elif "running" in statuses:
                title = steps[statuses.index("running")]
                text = (
                    "Classifying"
                    if title.startswith("Classify")
                    else "Downloading"
                    if title.startswith("Download")
                    else "Validating"
                    if title == "Validate input"
                    else "Creating images"
                )
            else:
                text = "Waiting"
            label_widget.setText(text)
            bar.setToolTip(f"{statuses.count('complete')} of {len(steps)} stages complete; not elapsed-time progress")

    def _event(self, kind, payload):
        if kind == "log":
            self.log.appendPlainText(str(payload))
        elif kind == "step":
            title, status = payload
            self.task_states[title] = status
            self._refresh_channel_progress()
            self.footer.setText(f"{title} · {status}")
        elif kind == "results":
            self._load_results(Path(payload))
        elif kind == "finished":
            status, message = payload
            self.activity_message.setText(message)
            self.footer.setText(message)
            self.setup.setEnabled(True)
            self.run_button.setEnabled(True)
            self.open_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            if status in {"cancelled", "failed"}:
                for steps in self.channel_steps.values():
                    for title in steps:
                        if self.task_states.get(title, "waiting") in {"waiting", "running"}:
                            self.task_states[title] = "cancelled"
                self._refresh_channel_progress()
            if status in {"complete", "partial"} and (self.runroot / "result.csv").exists():
                self._load_results(self.runroot / "result.csv")
            if self._closing:
                self.close()

    _closing = False

    def _cancel(self):
        if self.worker:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.activity_message.setText("Stopping workers and preserving completed artifacts…")

    def closeEvent(self, event):
        if self.worker_thread and self.worker_thread.is_alive():
            if (
                self._closing
                or QMessageBox.question(self, "Stop active run?", "Stop the current run and close DLYSO?")
                == QMessageBox.StandardButton.Yes
            ):
                self._closing = True
                self._cancel()
                QTimer.singleShot(250, self.close)
            event.ignore()
        else:
            event.accept()

    def _open_project(self):
        path = QFileDialog.getExistingDirectory(self, "Open DLYSO project")
        if path:
            self.open_project(Path(path))

    def open_project(self, path):
        try:
            config_path = path / "project.json"
            config = json.loads(config_path.read_text()) if config_path.exists() else {}
            if not config and not (path / "coords_normalized.csv").exists():
                raise ValueError("This is not a DLYSO project folder.")
            self.runroot = path
            self.name_edit.setText(config.get("project", path.name))
            self.input_edit.setText(config.get("input_csv", ""))
            self.output_edit.setText(str(path.parent))
            self.project_tag.setText(path.name)
            for key, card in self.cards.items():
                card.check.setChecked(key in config.get("modalities", ["SEDplot"]))
            self.workers.setValue(config.get("workers", 4))
            self.batch.setValue(config.get("batch_size", 16))
            self.classify_check.setChecked(config.get("classification", True))
            log = path / "pipeline.log"
            self.log.setPlainText(
                log.read_text(errors="replace")[-100000:] if log.exists() else "No saved activity log."
            )
            if (path / "result.csv").exists():
                self._load_results(path / "result.csv")
                self._navigate(2)
            else:
                self.results = pd.DataFrame()
                self._filter_results()
                self._navigate(0)
            self.footer.setText(f"Opened {path}")
        except (OSError, ValueError) as exc:
            self._error(str(exc))

    def _load_results(self, path):
        try:
            frame = pd.read_csv(path)
            if not {"ra", "dec"}.issubset(frame.columns):
                raise ValueError("Results must contain ra and dec columns.")
            self.results = frame
            # Upgrade the view/export of legacy tables without changing their
            # source file: no-data rows must never be exported as zero votes.
            for modality in MODALITIES:
                columns = self._prob_columns(modality)
                if columns or f"{modality}_votes" in frame:
                    count = frame[columns].notna().sum(axis=1)
                    frame[f"{modality}_n_models"] = count
                    frame[f"{modality}_status"] = count.map(
                        lambda n: "complete" if n == 12 else ("partial" if n else "not_evaluated")
                    )
                    if f"{modality}_votes" in frame:
                        frame[f"{modality}_votes"] = frame[f"{modality}_votes"].where(count > 0).astype("Int64")
            self.preview_cache = {}
            self.export_button.setEnabled(True)
            self.result_button.setEnabled(True)
            self._filter_results()
        except (OSError, ValueError) as exc:
            self._error(f"Cannot open results: {exc}")

    def _prob_columns(self, modality):
        from scripts.combineresult import THRESHOLDS

        return [f"{modality}_{m}" for m in THRESHOLDS[modality] if f"{modality}_{m}" in self.results]

    def _filter_results(self):
        if self.results.empty:
            self.table.setModel(CatalogueModel())
            self.source_title.setText("Source detail")
            self.image.clear()
            self.image.setText("Open a result catalogue\nto inspect a source.")
            self.scores.clear()
            for value in self.metrics.values():
                value.setText("—")
            self.export_button.setEnabled(False)
            self.result_button.setEnabled(False)
            self.results_note.setText("No result table in this project yet.")
            return
        modality = self.result_modality.currentData()
        probabilities = self.results[self._prob_columns(modality)]
        count = probabilities.notna().sum(axis=1)
        self.metrics["sources"].setText(f"{len(self.results):,}")
        self.metrics["evaluated"].setText(f"{int((count > 0).sum()):,}")
        self.metrics["missing"].setText(f"{int((count == 0).sum()):,}")
        self.results_note.setText(
            f"{MODALITIES[modality]} · blank votes mean no evaluation. Partial coverage is shown explicitly."
        )
        identifier = next((c for c in ["source_id", "name", "Name", "ID", "id"] if c in self.results), None)
        view = pd.DataFrame(index=self.results.index)
        view["Source"] = (
            self.results[identifier].astype(str) if identifier else [f"Source {i + 1:04d}" for i in range(len(view))]
        )
        view["RA / deg"] = self.results["ra"]
        view["Dec / deg"] = self.results["dec"]
        votes = self.results.get(f"{modality}_votes", pd.Series(np.nan, index=view.index))
        view["Votes"] = votes.where(count > 0)
        view["Models"] = count
        view["Coverage"] = count.map(lambda n: "Complete" if n == 12 else ("Partial" if n else "Not evaluated"))
        query = self.search.text().strip().lower()
        if query:
            mask = view.astype(str).apply(lambda col: col.str.lower().str.contains(query, regex=False)).any(axis=1)
            view = view[mask]
        self.table.setModel(CatalogueModel(view))
        self.table.model().layoutChanged.connect(self._source_selected)
        self.table.selectionModel().selectionChanged.connect(self._source_selected)
        if len(view):
            self.table.selectRow(0)
        else:
            self.source_title.setText("No matching sources")
            self.image.clear()
            self.scores.clear()

    def _source_selected(self, *_):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return
        model = self.table.model()
        index = model.frame.index[selected[0].row()]
        row = self.results.loc[index]
        self.source_title.setText(str(model.frame.loc[index, "Source"]))
        modality = self.result_modality.currentData()
        columns = self._prob_columns(modality)
        from scripts.combineresult import THRESHOLDS

        parts = [
            "<style>td { padding: 4px 2px; } th { text-align:left; color:#65777c; }</style>",
            "<table width='100%'><tr><th>Model</th><th>Score</th></tr>",
        ]
        for name in THRESHOLDS[modality]:
            column = f"{modality}_{name}"
            value = row.get(column, np.nan)
            text = "—" if pd.isna(value) else f"{value:.3f}"
            parts.append(f"<tr><td>{name.replace('custom_', '').replace('_', ' ')}</td><td>{text}</td></tr>")
        parts.append("</table>")
        if not columns or row[columns].isna().all():
            parts.insert(1, "<p>No predictions for this channel.</p>")
        self.scores.setHtml("".join(parts))
        self.image.clear()
        image_path = None
        if self.runroot:
            if modality not in self.preview_cache:
                mapping = {}
                for path in (self.runroot / modality).glob("*.png"):
                    try:
                        ra, dec = map(float, path.stem.split("_", 1))
                        mapping[(round(ra, 6), round(dec, 6))] = path
                    except ValueError:
                        continue
                self.preview_cache[modality] = mapping
            image_path = self.preview_cache[modality].get((round(row["ra"], 6), round(row["dec"], 6)))
        if image_path:
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                self.image.setPixmap(
                    pixmap.scaled(
                        230, 195, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    )
                )
                return
        self.image.setText("No image available\nfor this data channel.")

    def _export_results(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export full result catalogue", "dlyso-results.csv", "CSV (*.csv)")
        if path:
            try:
                self.results.to_csv(path, index=False)
                self.footer.setText(f"Exported all {len(self.results):,} sources to {path}")
            except OSError as exc:
                self._error(str(exc))

    def _save_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save activity log", "dlyso-activity.log", "Log (*.log)")
        if path:
            try:
                full_log = self.runroot / "pipeline.log" if self.runroot else None
                text = full_log.read_text() if full_log and full_log.exists() else self.log.toPlainText()
                Path(path).write_text(text, encoding="utf-8")
                self.footer.setText(f"Saved activity log to {path}")
            except OSError as exc:
                self._error(str(exc))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("DLYSO")
    app.setOrganizationName("DLYSO")
    app.setStyle("Fusion")
    app.setPalette(gui_palette())
    window = DlysoApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
