import threading
import time
import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QMessageBox, QFileDialog, QAbstractItemView
from src.data.data_loader import DataSourceConfig
from src.ui.table_models import SORT_ROLE
from src.ui.ui_main_window import MainWindow


@pytest.fixture
def window(qtbot, monkeypatch):
    messages = []
    for kind in ('critical', 'warning', 'information'):
        monkeypatch.setattr(QMessageBox, kind, lambda *args, _kind=kind, **kwargs: messages.append((_kind, args[2])))
    w = MainWindow()
    w.messages = messages
    qtbot.addWidget(w)
    yield w
    if w._worker is not None:
        qtbot.waitUntil(lambda: not w._busy, timeout=10000)


def wait(qtbot, window):
    qtbot.waitUntil(lambda: not window._busy, timeout=10000)


@pytest.fixture
def loaded(window, qtbot, csv_config):
    assert window.import_source(csv_config)
    wait(qtbot, window)
    assert window._state is not None, window.messages
    return window


def view_snapshot(w):
    return (w._state, w._repo, w._current_filter,
            tuple(t.model() for t in (w.data_table, w.kpi_table, w.rfm_table)),
            w.report_view.toPlainText(), w._filter_snapshot(), w._revision,
            w.graph_canvas, w._graph_key)


def fail(*args, **kwargs):
    raise RuntimeError('injected failure')


def test_no_data_graph_actions_disabled(window):
    assert not window.build_graph_btn.isEnabled()
    assert not window.save_graph_btn.isEnabled()
    assert not window.gen_report_action.isEnabled()
    window._on_save_graph()
    assert window.messages[-1][0] == 'warning'


def test_import_and_reset_use_dataset_dates(loaded, qtbot):
    w = loaded
    assert w.date_from_edit.date() == QDate(2025, 1, 1)
    assert w.date_to_edit.date() == QDate(2025, 1, 3)
    w.date_from_edit.setDate(QDate(2025, 1, 2))
    w.date_to_edit.setDate(QDate(2025, 1, 2))
    w._on_apply_filters()
    wait(qtbot, w)
    assert len(w._state.frame) == 2
    w._on_reset_filters()
    wait(qtbot, w)
    assert w._current_filter is None
    assert w.date_from_edit.date() == QDate(2025, 1, 1)
    assert w.date_to_edit.date() == QDate(2025, 1, 3)
    assert len(w._state.frame) == 4


def test_reverse_range_is_rejected_without_mutation(loaded):
    w = loaded
    before = view_snapshot(w)
    w.date_from_edit.setDate(QDate(2025, 1, 3))
    w.date_to_edit.setDate(QDate(2025, 1, 1))
    w._on_apply_filters()
    assert not w._busy
    assert view_snapshot(w) == before
    assert 'later' in w.messages[-1][1]


@pytest.mark.parametrize('failure_point', ['load', 'repository', 'kpi', 'rfm', 'markdown', 'data_model', 'rfm_model', 'publish'])
def test_failed_import_preserves_everything(loaded, qtbot, csv_config, monkeypatch, failure_point):
    import services.services as services
    import ui.ui_main_window as ui
    w = loaded
    w.category_combo.setCurrentIndex(1)
    w._on_apply_filters()
    wait(qtbot, w)
    w._on_build_graph()
    before = view_snapshot(w)
    if failure_point == 'load':
        monkeypatch.setattr(services.DataLoader, 'load_data', fail)
    elif failure_point == 'repository':
        monkeypatch.setattr(services, 'SalesRepository', fail)
    elif failure_point in ('kpi', 'rfm'):
        monkeypatch.setattr(services, 'calculate_' + failure_point + '_results', fail)
    elif failure_point == 'markdown':
        monkeypatch.setattr(services, 'generate_markdown_report', fail)
    elif failure_point in ('data_model', 'rfm_model'):
        monkeypatch.setattr(ui, failure_point, fail)
    else:
        # Simulates a failure AFTER one live table has already been changed.
        def partial(models):
            w.data_table.setModel(models[0])
            raise RuntimeError('partial publication')
        monkeypatch.setattr(w, '_set_models', partial)
    w.import_source(csv_config)
    wait(qtbot, w)
    assert view_snapshot(w) == before
    assert w.save_graph_btn.isEnabled()
    assert w.messages[-1][0] == 'critical'
    assert not any(kind == 'information' for kind, _ in w.messages)


def test_invalid_file_import_preserves_filter(loaded, qtbot, tmp_path):
    w = loaded
    w.customer_combo.setCurrentIndex(1)
    w._on_apply_filters()
    wait(qtbot, w)
    before = view_snapshot(w)
    path = tmp_path / 'bad.csv'
    path.write_text('wrong\nvalue\n')
    w.import_source(DataSourceConfig('csv', path))
    wait(qtbot, w)
    assert view_snapshot(w) == before


@pytest.mark.parametrize('stage', ['filter', 'kpi', 'rfm', 'markdown', 'publication'])
def test_filter_failures_preserve_committed_state(loaded, qtbot, monkeypatch, stage):
    import services.services as services
    w = loaded
    w._on_build_graph()
    before = view_snapshot(w)
    if stage == 'filter':
        monkeypatch.setattr(w._repo, 'filtered', fail)
    elif stage in ('kpi', 'rfm'):
        monkeypatch.setattr(services, f'calculate_{stage}_results', fail)
    elif stage == 'markdown':
        monkeypatch.setattr(services, 'generate_markdown_report', fail)
    else:
        monkeypatch.setattr(w, '_set_models', fail)
    w.category_combo.setCurrentIndex(1)
    w._on_apply_filters()
    wait(qtbot, w)
    assert view_snapshot(w) == before
    assert w.messages[-1][0] == 'critical'


def test_reset_failure_does_not_change_filters(loaded, qtbot, monkeypatch):
    import services.services as services
    w = loaded
    w.category_combo.setCurrentIndex(1)
    w._on_apply_filters()
    wait(qtbot, w)
    before = view_snapshot(w)
    monkeypatch.setattr(services, 'generate_markdown_report', fail)
    w._on_reset_filters()
    wait(qtbot, w)
    assert view_snapshot(w) == before


@pytest.mark.parametrize('operation', ['import', 'filter', 'reset'])
def test_successful_data_change_clears_graph(loaded, qtbot, csv_config, operation):
    w = loaded
    w._on_build_graph()
    assert w.save_graph_btn.isEnabled()
    assert w.graph_axes.has_data()
    if operation == 'import':
        w.import_source(csv_config)
    elif operation == 'filter':
        w.category_combo.setCurrentIndex(1)
        w._on_apply_filters()
    else:
        w._on_reset_filters()
    wait(qtbot, w)
    assert not w.graph_axes.has_data()
    assert w._graph_key is None
    assert not w.save_graph_btn.isEnabled()
    assert w.build_graph_btn.isEnabled()


def test_empty_slice_clears_and_prevents_save(loaded, qtbot, monkeypatch):
    w = loaded
    w._on_build_graph()
    w.date_from_edit.setDate(QDate(2024, 1, 1))
    w.date_to_edit.setDate(QDate(2024, 1, 2))
    w._on_apply_filters()
    wait(qtbot, w)
    assert w._state.frame.empty
    assert not w.graph_axes.has_data()
    assert not w.build_graph_btn.isEnabled()
    assert not w.save_graph_btn.isEnabled()
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', fail)
    w._on_save_graph()  # Must not even open the dialog.
    assert w.messages[-1][0] == 'warning'
    w._on_build_graph()
    assert not w.graph_axes.has_data()


def test_graph_choice_change_and_failed_build_disable_save(loaded):
    w = loaded
    w._on_build_graph()
    assert w.save_graph_btn.isEnabled()
    w.graph_type_combo.setCurrentIndex(2)  # Pie + time series is intentionally unsupported.
    assert not w.save_graph_btn.isEnabled()
    assert not w.graph_axes.has_data()
    w._on_build_graph()
    assert not w.save_graph_btn.isEnabled()
    assert not w.graph_axes.has_data()
    assert w.messages[-1][0] == 'critical'


def test_graph_rendering_failure_clears_old_chart(loaded, monkeypatch):
    w = loaded
    w._on_build_graph()
    original = w._new_canvas
    def broken():
        canvas, axes = original()
        monkeypatch.setattr(canvas, 'draw', fail)
        return canvas, axes
    monkeypatch.setattr(w, '_new_canvas', broken)
    w._on_build_graph()
    assert not w.graph_axes.has_data()
    assert w._graph_key is None
    assert not w.save_graph_btn.isEnabled()


def test_raw_numeric_and_date_sorting_and_readonly(loaded):
    w = loaded
    model = w.data_table.model()
    quantity = next(i for i in range(model.columnCount()) if model.headerData(i, Qt.Orientation.Horizontal) == 'quantity')
    dates = next(i for i in range(model.columnCount()) if model.headerData(i, Qt.Orientation.Horizontal) == 'sale_date')
    model.sort(quantity, Qt.SortOrder.AscendingOrder)
    assert [model.item(i, quantity).data(SORT_ROLE) for i in range(4)] == [1, 2, 3, 10]
    model.sort(dates, Qt.SortOrder.DescendingOrder)
    values = [model.item(i, dates).data(SORT_ROLE) for i in range(4)]
    assert values == sorted(values, reverse=True)
    for table, col in ((w.kpi_table, 1), (w.rfm_table, 3)):
        model = table.model()
        model.sort(col, Qt.SortOrder.AscendingOrder)
        values = [model.item(i, col).data(SORT_ROLE) for i in range(model.rowCount())]
        assert values == sorted(values)
        assert table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
        for r in range(model.rowCount()):
            for c in range(model.columnCount()):
                assert not model.item(r, c).isEditable()


@pytest.mark.parametrize('html', [False, True])
@pytest.mark.parametrize('stage', ['filter', 'kpi', 'rfm', 'generate', 'write'])
def test_export_errors_no_false_success_or_state_change(loaded, qtbot, tmp_path, monkeypatch, html, stage):
    import services.services as services
    w = loaded
    w.category_combo.setCurrentIndex(1)
    w._on_apply_filters()
    wait(qtbot, w)
    w._on_build_graph()
    before = view_snapshot(w)
    path = tmp_path / ('report.html' if html else 'report.md')
    path.write_text('OLD')
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(path), ''))
    if stage == 'filter':
        monkeypatch.setattr(w._repo, 'filtered', fail)
    elif stage in ('kpi', 'rfm'):
        monkeypatch.setattr(services, f'calculate_{stage}_results', fail)
    elif stage == 'generate':
        monkeypatch.setattr(services, 'generate_html_report' if html else 'generate_markdown_report', fail)
    else:
        monkeypatch.setattr(services.os, 'replace', fail)
    (w._on_generate_html_report if html else w._on_generate_report)()
    wait(qtbot, w)
    assert view_snapshot(w) == before
    assert path.read_text() == 'OLD'
    assert {p.name for p in tmp_path.iterdir()} == {path.name, 'sales.csv'}
    assert w.messages[-1][0] == 'critical'
    assert not any(kind == 'information' for kind, _ in w.messages)


@pytest.mark.parametrize('html', [False, True])
def test_report_export_success(loaded, qtbot, tmp_path, monkeypatch, html):
    w = loaded
    path = tmp_path / ('report.html' if html else 'report.md')
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(path), ''))
    (w._on_generate_html_report if html else w._on_generate_report)()
    wait(qtbot, w)
    assert path.exists()
    assert ('<!DOCTYPE html>' if html else '# Sales report') in path.read_text()
    assert w.messages[-1][0] == 'information'


def test_graph_save_current_success(loaded, qtbot, tmp_path, monkeypatch):
    w = loaded
    w._on_build_graph()
    path = tmp_path / 'graph.png'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(path), ''))
    w._on_save_graph()
    wait(qtbot, w)
    assert path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    assert w.messages[-1][0] == 'information'


def test_graph_save_write_failure(loaded, qtbot, tmp_path, monkeypatch):
    import services.services as services
    w = loaded
    w._on_build_graph()
    before = view_snapshot(w)
    path = tmp_path / 'graph.png'
    path.write_bytes(b'OLD')
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(path), ''))
    monkeypatch.setattr(services.os, 'replace', fail)
    w._on_save_graph()
    wait(qtbot, w)
    assert path.read_bytes() == b'OLD'
    assert view_snapshot(w) == before
    assert w.messages[-1][0] == 'critical'
    assert not any(kind == 'information' for kind, _ in w.messages)


def test_import_uses_worker_not_gui_thread(loaded, qtbot, csv_config, monkeypatch):
    w = loaded
    thread_ids = []
    original = w._service.prepare_import
    def slow(config):
        thread_ids.append(threading.get_ident())
        time.sleep(0.03)
        return original(config)
    monkeypatch.setattr(w._service, 'prepare_import', slow)
    w.import_source(csv_config)
    assert w._busy
    assert not w.import_csv_action.isEnabled()
    assert not w.build_graph_btn.isEnabled()
    assert not w.import_source(csv_config)  # Serialized, no racing tasks.
    wait(qtbot, w)
    assert thread_ids and thread_ids[0] != threading.get_ident()
    assert w.build_graph_btn.isEnabled()


def test_close_during_task_waits_safely(window, qtbot, csv_config, monkeypatch):
    w = window
    original = w._service.prepare_import
    def slow(config):
        time.sleep(0.05)
        return original(config)
    monkeypatch.setattr(w._service, 'prepare_import', slow)
    w.show()
    w.import_source(csv_config)
    w.close()
    assert w._closing
    wait(qtbot, w)
    qtbot.waitUntil(lambda: not w.isVisible(), timeout=5000)


def test_empty_import_and_reset(loaded, qtbot, tmp_path):
    w = loaded
    w._on_build_graph()
    path = tmp_path / 'empty.csv'
    path.write_text('sale_date,customer_id,category,total_price\n')
    w.import_source(DataSourceConfig('csv', path))
    wait(qtbot, w)
    assert w._state.frame.empty
    assert not w.date_from_edit.isEnabled()
    assert w.date_from_edit.specialValueText() == 'No data'
    assert not w.graph_axes.has_data()
    assert not w.build_graph_btn.isEnabled()
    assert not w.save_graph_btn.isEnabled()
    w._on_reset_filters()
    wait(qtbot, w)
    assert w._state.frame.empty
    assert not w.save_graph_btn.isEnabled()


@pytest.mark.parametrize('data_choice,chart_type', [(0, 0), (0, 1), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)])
def test_existing_supported_graphs(loaded, data_choice, chart_type):
    w = loaded
    w.graph_data_combo.setCurrentIndex(data_choice)
    w.graph_type_combo.setCurrentIndex(chart_type)
    w._on_build_graph()
    assert w.graph_axes.has_data()
    assert w.save_graph_btn.isEnabled()
    assert not w.messages


@pytest.mark.parametrize('handler', ['_on_import_csv', '_on_import_sqlite', '_on_generate_report', '_on_generate_html_report', '_on_save_graph'])
def test_file_dialog_errors_are_caught(loaded, monkeypatch, handler):
    w = loaded
    w._on_build_graph()
    before = view_snapshot(w)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', fail)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', fail)
    getattr(w, handler)()
    assert view_snapshot(w) == before
    assert w.messages[-1][0] == 'critical'


def test_report_cancel_has_no_success(loaded, monkeypatch):
    w = loaded
    before = view_snapshot(w)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: ('', ''))
    w._on_generate_report()
    assert view_snapshot(w) == before
    assert not w.messages


def test_thread_start_failure_does_not_lock_ui(loaded, csv_config, monkeypatch):
    import ui.ui_main_window as ui
    w = loaded
    before = view_snapshot(w)
    monkeypatch.setattr(ui.TaskThread, 'start', fail)
    w.import_source(csv_config)
    assert not w._busy
    assert w.import_csv_action.isEnabled()
    assert view_snapshot(w) == before
    assert w.messages[-1][0] == 'critical'


def test_filter_control_publication_failure_rolls_back(loaded, qtbot, csv_config, monkeypatch):
    w = loaded
    w._on_build_graph()
    before = view_snapshot(w)
    original = w._set_filter_controls
    def partial(state):
        original(state)
        w.date_from_edit.setDate(QDate(2020, 1, 1))
        raise RuntimeError('filter widget publication failed')
    monkeypatch.setattr(w, '_set_filter_controls', partial)
    w.import_source(csv_config)
    wait(qtbot, w)
    assert view_snapshot(w) == before


def test_graph_build_exception_is_caught(loaded, monkeypatch):
    import ui.ui_main_window as ui
    w = loaded
    w._on_build_graph()
    monkeypatch.setattr(ui, 'build_graph', fail)
    w._on_build_graph()
    assert not w.save_graph_btn.isEnabled()
    assert not w.graph_axes.has_data()
    assert w.messages[-1][0] == 'critical'


def test_original_category_line_restriction_preserved(loaded):
    w = loaded
    w.graph_data_combo.setCurrentIndex(1)
    w.graph_type_combo.setCurrentIndex(0)
    w._on_build_graph()
    assert not w.save_graph_btn.isEnabled()
    assert 'use bar or pie' in w.messages[-1][1]


def test_failed_task_then_successful_import_recovers(loaded, qtbot, tmp_path, csv_config):
    w = loaded
    bad = tmp_path / 'bad.csv'
    bad.write_text('invalid\nrow\n')
    w.import_source(DataSourceConfig('csv', bad))
    wait(qtbot, w)
    assert w.import_csv_action.isEnabled()
    w.messages.clear()
    w.import_source(csv_config)
    wait(qtbot, w)
    assert len(w._state.frame) == 4
    assert not w.messages
    assert w.build_graph_btn.isEnabled()


def test_workflow_calculations_not_on_gui_thread(loaded, qtbot, tmp_path, monkeypatch):
    import services.services as services
    w = loaded
    gui_thread = threading.get_ident()
    calls = []
    original_kpi, original_rfm, original_md = services.calculate_kpi_results, services.calculate_rfm_results, services.generate_markdown_report
    def wrapper(name, original):
        def wrapped(*args, **kwargs):
            calls.append((name, threading.get_ident()))
            return original(*args, **kwargs)
        return wrapped
    monkeypatch.setattr(services, 'calculate_kpi_results', wrapper('kpi', original_kpi))
    monkeypatch.setattr(services, 'calculate_rfm_results', wrapper('rfm', original_rfm))
    monkeypatch.setattr(services, 'generate_markdown_report', wrapper('md', original_md))
    w.category_combo.setCurrentIndex(1)
    w._on_apply_filters()
    wait(qtbot, w)
    path = tmp_path / 'report.md'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(path), ''))
    w._on_generate_report()
    wait(qtbot, w)
    assert len(calls) == 6
    assert {name for name, _ in calls} == {'kpi', 'rfm', 'md'}
    assert all(thread_id != gui_thread for _, thread_id in calls)


def test_all_publication_widgets_updated_on_gui_thread(loaded, qtbot, csv_config, monkeypatch):
    w = loaded
    original = w._commit_state
    threads = []
    def commit(candidate):
        threads.append(threading.get_ident())
        original(candidate)
    monkeypatch.setattr(w, '_commit_state', commit)
    w.import_source(csv_config)
    wait(qtbot, w)
    assert threads == [threading.get_ident()]


def test_sqlite_import_dialog_workflow(window, qtbot, tmp_path, monkeypatch):
    import sqlite3
    from contextlib import closing
    from PySide6.QtWidgets import QInputDialog
    path = tmp_path / 'sales.db'
    with closing(sqlite3.connect(path)) as conn:
        conn.execute('CREATE TABLE " sales " (sale_date TEXT, customer_id TEXT, category TEXT, total_price REAL)')
        conn.execute("INSERT INTO \" sales \" VALUES ('2025-01-01', '0001', 'A', 5)")
        conn.commit()
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
    monkeypatch.setattr(QInputDialog, 'getText', lambda *args, **kwargs: (' sales ', True))
    window._on_import_sqlite()
    wait(qtbot, window)
    assert window._state.frame.customer_id.iloc[0] == '0001'
    assert window._state.kpi.total_revenue == 5
    assert not window.messages


def test_csv_import_dialog_workflow(window, qtbot, csv_config, monkeypatch):
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(csv_config.path), ''))
    window._on_import_csv()
    wait(qtbot, window)
    assert len(window._state.frame) == 4
    assert not window.messages


def test_png_render_failure_does_not_write(loaded, tmp_path, monkeypatch):
    w = loaded
    w._on_build_graph()
    before = view_snapshot(w)
    path = tmp_path / 'graph.png'
    path.write_bytes(b'OLD')
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(path), ''))
    monkeypatch.setattr(w.graph_canvas.figure, 'savefig', fail)
    w._on_save_graph()
    assert path.read_bytes() == b'OLD'
    assert view_snapshot(w) == before
    assert w.messages[-1][0] == 'critical'
    assert not any(kind == 'information' for kind, _ in w.messages)
