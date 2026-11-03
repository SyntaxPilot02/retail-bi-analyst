"""GUI controller: serialized QThread use cases and transactional publication.

Public MainWindow and original handler names remain available. Pure visual layout
is in ui_view; business workflows are in services. All widgets, Qt models and
Matplotlib figures are accessed on the GUI thread only.
"""
from __future__ import annotations
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QDate, Slot
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QAbstractItemView
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from src.config import REPORT_FILENAME, REPORT_HTML_FILENAME
from src.data.data_loader import DataSourceConfig
from src.data.repository import SalesFilter
from src.services.services import AnalysisService, PreparedState, atomic_write
from src.ui.table_models import data_model, kpi_model, rfm_model
from src.ui.ui_view import MainWindowView
from src.ui.workers import TaskThread
from src.visualization.graphs import build_graph


class MainWindow(MainWindowView):
    def __init__(self) -> None:
        super().__init__()
        self._repo = None
        self._current_filter = None
        self._state = None
        self._service = AnalysisService()
        self._worker = None
        self._completion = None
        self._failure = None
        self._busy = False
        self._closing = False
        self._revision = 0
        self._graph_key = None
        self.import_csv_action.triggered.connect(self._on_import_csv)
        self.import_sqlite_action.triggered.connect(self._on_import_sqlite)
        self.gen_report_action.triggered.connect(self._on_generate_report)
        self.gen_html_report_action.triggered.connect(self._on_generate_html_report)
        self.exit_action.triggered.connect(self.close)
        self.apply_filters_btn.clicked.connect(self._on_apply_filters)
        self.reset_filters_btn.clicked.connect(self._on_reset_filters)
        self.build_graph_btn.clicked.connect(self._on_build_graph)
        self.save_graph_btn.clicked.connect(self._on_save_graph)
        self.graph_data_combo.currentIndexChanged.connect(self._on_graph_choice_changed)
        self.graph_type_combo.currentIndexChanged.connect(self._on_graph_choice_changed)
        for table in (self.data_table, self.kpi_table, self.rfm_table):
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for edit in (self.date_from_edit, self.date_to_edit):
            edit.setDateRange(QDate(1677, 9, 21), QDate(2262, 4, 11))
        self._refresh_enabled()

    def _error(self, context, error):
        if not self._closing:
            QMessageBox.critical(self, 'Error', f'{context}\n{error}')

    def _refresh_enabled(self):
        ready = not self._busy
        has_repo = self._state is not None
        has_rows = has_repo and not self._state.frame.empty
        for action in (self.import_csv_action, self.import_sqlite_action):
            action.setEnabled(ready)
        self.gen_report_action.setEnabled(ready and has_repo)
        self.gen_html_report_action.setEnabled(ready and has_rows)
        for widget in (self.category_combo, self.customer_combo, self.apply_filters_btn, self.reset_filters_btn):
            widget.setEnabled(ready and has_repo)
        for edit in (self.date_from_edit, self.date_to_edit):
            edit.setEnabled(ready and has_repo and self._state.date_min is not None)
        for combo in (self.graph_data_combo, self.graph_type_combo):
            combo.setEnabled(ready and has_rows)
        self.build_graph_btn.setEnabled(ready and has_rows)
        self.save_graph_btn.setEnabled(ready and has_rows and self._graph_key == self._expected_graph_key())

    def _expected_graph_key(self):
        return (self._revision, self.graph_data_combo.currentText(), self.graph_type_combo.currentText())

    def _run(self, context, task, complete, failure=None):
        if self._busy:
            return False
        self._busy = True
        self._completion = complete
        self._failure = failure
        self._task_context = context
        self._refresh_enabled()
        try:
            worker = TaskThread(task, self)
            self._worker = worker
            worker.succeeded.connect(self._task_succeeded)
            worker.failed.connect(self._task_failed)
            worker.finished.connect(self._task_finished)
            worker.start()
        except Exception as exc:
            self._worker = None
            self._busy = False
            self._handle_task_failure(exc)
            if 'worker' in locals():
                worker.deleteLater()
            self._refresh_enabled()
            return False
        return True

    @Slot(object)
    def _task_succeeded(self, result):
        if self._closing:
            return
        try:
            self._completion(result)
        except Exception as exc:
            self._handle_task_failure(exc)

    @Slot(str)
    def _task_failed(self, error):
        if self._closing:
            return
        self._handle_task_failure(error)

    def _handle_task_failure(self, error):
        message = str(error)
        if self._failure:
            try:
                self._failure()
            except Exception as restore_error:
                message += f'\nFilter control restore failed: {restore_error}'
        self._error(self._task_context, message)

    @Slot()
    def _task_finished(self):
        worker = self._worker
        self._worker = None
        self._busy = False
        self._completion = self._failure = None
        self._refresh_enabled()
        if worker is not None:
            worker.deleteLater()
        if self._closing:
            self.close()

    def closeEvent(self, event):
        # Never terminate a running thread or destroy it while SQLite/files are open.
        if self._worker is not None:
            self._closing = True
            event.ignore()
            self.setEnabled(False)
            return
        event.accept()

    def import_source(self, config: DataSourceConfig):
        """Asynchronous equivalent of the original import handlers, also testable."""
        return self._run('Import failed; previous dataset was preserved.',
                         lambda: self._service.prepare_import(config), self._commit_state)

    def _on_import_csv(self):
        try:
            if self._busy:
                return
            path, _ = QFileDialog.getOpenFileName(self, 'Choose CSV File', '', 'CSV Files (*.csv);;All Files (*)')
            if path:
                self.import_source(DataSourceConfig('csv', Path(path)))
        except Exception as exc:
            self._error('Import failed; previous dataset was preserved.', exc)

    def _on_import_sqlite(self):
        try:
            if self._busy:
                return
            path, _ = QFileDialog.getOpenFileName(self, 'Choose SQLite Database', '', 'SQLite Files (*.db *.sqlite);;All Files (*)')
            if not path:
                return
            name, ok = QInputDialog.getText(self, 'Table Name', 'Enter table name in the database:', text='sales')
            if ok and name:
                # Exact name, not stripped: names with spaces are valid SQLite identifiers.
                self.import_source(DataSourceConfig('sqlite', Path(path), name))
        except Exception as exc:
            self._error('Import failed; previous dataset was preserved.', exc)

    def _read_filter(self):
        start, end = self.date_from_edit.date(), self.date_to_edit.date()
        if start > end:
            raise ValueError('Start date must not be later than end date')
        return SalesFilter(datetime(start.year(), start.month(), start.day()),
                           datetime(end.year(), end.month(), end.day()),
                           self.category_combo.currentData(), self.customer_combo.currentData())

    def _on_apply_filters(self):
        try:
            if self._repo is None or self._busy:
                return
            flt = self._read_filter()
            repo = self._repo
            self._run('Filtering failed; previous results were preserved.',
                      lambda: self._service.prepare(repo, flt), self._commit_state,
                      self._restore_committed_filters)
        except Exception as exc:
            self._restore_committed_filters()
            self._error('Filtering failed; previous results were preserved.', exc)

    def _on_reset_filters(self):
        try:
            if self._repo is None or self._busy:
                return
            repo = self._repo
            self._run('Reset failed; previous results were preserved.',
                      lambda: self._service.prepare(repo, None), self._commit_state,
                      self._restore_committed_filters)
        except Exception as exc:
            self._error('Reset failed; previous results were preserved.', exc)

    def _populate_filters(self):
        if self._state is not None:
            self._set_filter_controls(self._state)

    def _set_filter_controls(self, state):
        for combo, title, values in ((self.category_combo, 'All Categories', state.categories),
                                     (self.customer_combo, 'All Customers', state.customers)):
            combo.clear()
            combo.addItem(title, None)
            for value in values:
                combo.addItem(value, value)
        for edit in (self.date_from_edit, self.date_to_edit):
            edit.setSpecialValueText('No data' if state.date_min is None else '')
        if state.date_min is None:
            self.date_from_edit.setDate(self.date_from_edit.minimumDate())
            self.date_to_edit.setDate(self.date_to_edit.minimumDate())
        else:
            flt = state.active_filter
            start = pd.Timestamp(flt.date_from) if flt and flt.date_from is not None else state.date_min
            end = pd.Timestamp(flt.date_to) if flt and flt.date_to is not None else state.date_max
            self.date_from_edit.setDate(QDate(start.year, start.month, start.day))
            self.date_to_edit.setDate(QDate(end.year, end.month, end.day))
        if state.active_filter:
            self.category_combo.setCurrentIndex(max(0, self.category_combo.findData(state.active_filter.category)))
            self.customer_combo.setCurrentIndex(max(0, self.customer_combo.findData(state.active_filter.customer_id)))

    def _restore_committed_filters(self):
        if self._state is not None:
            self._set_filter_controls(self._state)

    def _filter_snapshot(self):
        combos = []
        for combo in (self.category_combo, self.customer_combo):
            combos.append(([(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())], combo.currentIndex()))
        dates = [(e.date(), e.specialValueText()) for e in (self.date_from_edit, self.date_to_edit)]
        return combos, dates

    def _restore_filter_snapshot(self, snapshot):
        combos, dates = snapshot
        for combo, (entries, selected) in zip((self.category_combo, self.customer_combo), combos):
            combo.clear()
            for title, value in entries:
                combo.addItem(title, value)
            combo.setCurrentIndex(selected)
        for edit, (value, special) in zip((self.date_from_edit, self.date_to_edit), dates):
            edit.setSpecialValueText(special)
            edit.setDate(value)

    def _new_canvas(self):
        canvas = FigureCanvas(Figure(figsize=(6, 4)))
        axes = canvas.figure.add_subplot(111)
        return canvas, axes

    def _swap_canvas(self, canvas, axes):
        old = self.graph_canvas
        self.graphs_layout.replaceWidget(old, canvas)
        old.hide()
        canvas.show()
        self.graph_canvas, self.graph_axes = canvas, axes
        return old

    def _set_models(self, models):
        for table, model in zip((self.data_table, self.kpi_table, self.rfm_table), models):
            table.setModel(model)
            table.resizeColumnsToContents()
            table.horizontalHeader().setStretchLastSection(True)

    def _commit_state(self, state: PreparedState):
        # Everything that can calculate/format/render is staged before touching live state.
        # This runs in the GUI thread; QStandardItemModel/QTextDocument never cross threads.
        models = (data_model(state.frame), kpi_model(state.kpi), rfm_model(state.rfm))
        document = QTextDocument(self)
        document.setMarkdown(state.markdown)
        canvas, axes = self._new_canvas()
        try:
            canvas.draw()
        except Exception:
            canvas.deleteLater()
            document.deleteLater()
            raise
        old_models = tuple(t.model() for t in (self.data_table, self.kpi_table, self.rfm_table))
        old_document = self.report_view.document()
        old_document.setParent(self)  # QTextEdit must not delete it before rollback is possible.
        old_canvas, old_axes = self.graph_canvas, self.graph_axes
        snapshot = self._filter_snapshot()
        try:
            self._set_models(models)
            self.report_view.setDocument(document)
            self._set_filter_controls(state)
            self._swap_canvas(canvas, axes)
        except Exception:
            # Roll back using primitive setters, not the possibly failing publication helper.
            for table, model in zip((self.data_table, self.kpi_table, self.rfm_table), old_models):
                table.setModel(model)
            self.report_view.setDocument(old_document)
            self._restore_filter_snapshot(snapshot)
            if self.graph_canvas is not old_canvas:
                self._swap_canvas(old_canvas, old_axes)
            canvas.deleteLater()
            document.deleteLater()
            raise
        self._state = state
        self._repo = state.repo
        self._current_filter = state.active_filter
        self._revision += 1
        self._graph_key = None
        old_canvas.deleteLater()
        old_document.deleteLater()
        for model in old_models:
            if model is not None:
                model.deleteLater()
        self._refresh_enabled()

    # Compatibility wrappers; calculations are not duplicated inside widgets.
    def _update_table(self, df):
        self.data_table.setModel(data_model(df))

    def _update_kpi_table(self, kpi):
        self.kpi_table.setModel(kpi_model(kpi))

    def _update_rfm_table(self, rfm):
        self.rfm_table.setModel(rfm_model(rfm))

    def _update_kpi_and_report(self, df=None):
        if self._repo is None or self._busy:
            return
        repo, flt = self._repo, self._current_filter
        # Preserve the old optional slice argument without mutating the repository.
        if df is None:
            task = lambda: self._service.prepare(repo, flt)
        else:
            from dataclasses import replace
            from data.repository import SalesRepository
            frame = df.copy(deep=True)
            date_min, date_max = self._state.date_min, self._state.date_max
            def task():
                candidate = self._service.prepare(SalesRepository(frame), None)
                return replace(candidate, repo=repo, active_filter=flt,
                               categories=repo.unique_categories(), customers=repo.unique_customers(),
                               date_min=date_min, date_max=date_max)
        self._run('Analysis failed; previous results were preserved.', task, self._commit_state)

    def _invalidate_graph(self):
        self._graph_key = None
        try:
            self.graph_axes.clear()
            self.graph_canvas.draw()
        finally:
            self._refresh_enabled()

    def _on_graph_choice_changed(self):
        try:
            self._invalidate_graph()
        except Exception as exc:
            self._error('Could not clear the graph. Saving is disabled.', exc)

    def _on_build_graph(self):
        if self._busy:
            return
        canvas = None
        try:
            self._graph_key = None
            if self._state is None or self._state.frame.empty:
                self._invalidate_graph()
                QMessageBox.warning(self, 'No Data', 'No rows available for visualization')
                return
            canvas, axes = self._new_canvas()
            build_graph(self._state.frame.copy(deep=True), self.graph_data_combo.currentText(),
                        self.graph_type_combo.currentText(), axes)
            canvas.draw()  # Rendering errors are failures too, not successful charts.
            old = self._swap_canvas(canvas, axes)
            old.deleteLater()
            self._graph_key = self._expected_graph_key()
        except Exception as exc:
            if canvas is not None and canvas is not self.graph_canvas:
                canvas.deleteLater()
            try:
                self._invalidate_graph()
            except Exception:
                pass
            self._error('Graph build failed. Saving is disabled.', exc)
        finally:
            self._refresh_enabled()

    def _on_save_graph(self):
        try:
            if self._busy:
                return
            if (self._state is None or self._state.frame.empty or self._graph_key is None
                    or self._graph_key != self._expected_graph_key()):
                QMessageBox.warning(self, 'No Graph', 'Build a current graph before saving')
                return
            path, _ = QFileDialog.getSaveFileName(self, 'Save graph', 'graph.png', 'PNG Files (*.png);;All Files (*)')
            if not path:
                return
            # Matplotlib is not thread safe: render on GUI thread, write bytes in worker.
            stream = BytesIO()
            self.graph_canvas.figure.savefig(stream, format='png', dpi=150)
            payload = stream.getvalue()
            self._run('Graph save failed.', lambda: atomic_write(Path(path), payload),
                      lambda _: QMessageBox.information(self, 'Success', 'Graph saved successfully'))
        except Exception as exc:
            self._error('Graph save failed.', exc)

    def _export_report(self, html=False):
        try:
            if self._busy:
                return
            if self._repo is None or (html and self._state.frame.empty):
                QMessageBox.warning(self, 'No Data', 'No rows available for report')
                return
            filename = REPORT_HTML_FILENAME if html else REPORT_FILENAME
            kind = 'HTML Files (*.html)' if html else 'Markdown File (*.md)'
            path, _ = QFileDialog.getSaveFileName(self, 'Save report', filename, kind + ';;All Files (*)')
            if not path:
                return
            repo, flt = self._repo, self._current_filter
            self._run('Report generation or write failed.',
                      lambda: self._service.export_report(repo, flt, Path(path), html),
                      lambda _: QMessageBox.information(self, 'Success', 'Report saved successfully'))
        except Exception as exc:
            self._error('Report generation or write failed.', exc)

    def _on_generate_report(self):
        self._export_report(False)

    def _on_generate_html_report(self):
        self._export_report(True)
