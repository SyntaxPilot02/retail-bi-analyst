import json
import re
import pytest
from analytics.analytics import KPIResult, RFMScores, calculate_rfm_results
from data.repository import SalesRepository
from reports.report_generator import generate_html_report, generate_markdown_report
from services.services import AnalysisService, atomic_write


def test_html_and_script_context_escaping(sales):
    payload = '</script><script>alert("x")</script>&\u2028\u2029'
    customer = '<img src=x onerror=alert(1)> & " \''
    rfm = {customer: RFMScores(1, 2, 3, payload)}
    html = generate_html_report(KPIResult(3, 3, 1, 1), rfm, SalesRepository(sales).raw)
    assert '<img src=x' not in html
    assert '&lt;img src=x' in html
    assert '&lt;/script&gt;' in html
    assert 'class="rfm-segment-Regular"' in html
    assert '<script>alert(' not in html
    encoded = re.search(r'const segmentLabels = (.*);', html).group(1)
    assert '<' not in encoded and '&' not in encoded and '\u2028' not in encoded
    assert json.loads(encoded) == [payload]
    assert '\\u003c/script\\u003e' in encoded


def test_markdown_cells_preserve_structure():
    cid = 'a\\|b\r\nc\rd\n<img src=x> & [link](x)'
    segment = 'Best|oops\n<script>x</script>'
    report = generate_markdown_report(KPIResult(3, 3, 1, 1), {cid: RFMScores(1, 1, 3, segment)})
    rows = [line for line in report.splitlines() if line.startswith('|')]
    assert len(rows) == 3
    assert all(line.count('|') == 6 for line in rows)
    assert '&#124;' in rows[2] and '<br>' in rows[2]
    assert '<img' not in report and '<script>' not in report
    assert '&lt;img' in report and '&#92;' in report


def test_atomic_write_failure_preserves_file(tmp_path, monkeypatch):
    import services.services as module
    target = tmp_path / 'existing.md'
    target.write_text('OLD')
    def fail(*args):
        raise PermissionError('denied')
    monkeypatch.setattr(module.os, 'replace', fail)
    with pytest.raises(PermissionError):
        atomic_write(target, b'NEW')
    assert target.read_text() == 'OLD'
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_report_roundtrip(tmp_path, sales):
    target = tmp_path / 'report.md'
    AnalysisService().export_report(SalesRepository(sales), None, target)
    assert 'Total revenue: **36.00**' in target.read_text()


def test_aggregation_overflow_is_not_published(sales):
    sales['total_price'] = 1e308
    with pytest.raises(ValueError, match='overflow'):
        AnalysisService().prepare(SalesRepository(sales), None)


def test_rfm_rules_unchanged():
    import pandas as pd
    from datetime import datetime
    rows = []
    for cid, count, day, amount in [('best', 5, '2025-12-31', 200), ('loyal', 3, '2025-11-01', 1),
                                     ('risk', 1, '2025-01-01', 1), ('regular', 1, '2025-12-31', 1)]:
        rows.extend([{'customer_id': cid, 'sale_date': pd.Timestamp(day), 'total_price': amount}] * count)
    result = calculate_rfm_results(pd.DataFrame(rows), datetime(2025, 12, 31))
    assert {k: v.segment for k, v in result.items()} == {'best': 'Best', 'loyal': 'Loyal', 'risk': 'At risk', 'regular': 'Regular'}


def test_category_aggregation_overflow_is_explicit():
    import pandas as pd
    frame = pd.DataFrame({'sale_date': ['2025-01-01'] * 4,
                          'customer_id': ['001'] * 4,
                          'category': ['A', 'A', 'B', 'B'],
                          'total_price': [1e308, 1e308, -1e308, -1e308]})
    with pytest.raises(ValueError, match='overflow'):
        AnalysisService().prepare(SalesRepository(frame), None)


def test_all_markdown_table_text_fields_are_escaped():
    score = RFMScores('1|2\n3', '5|6\r7', 3, 'Regular')
    md = generate_markdown_report(KPIResult(3, 3, 1, 1), {'001': score})
    rows = [line for line in md.splitlines() if line.startswith('|')]
    assert len(rows) == 3
    assert rows[2].count('|') == 6


def test_html_dynamic_date_fallback_escaped():
    import pandas as pd
    payload = '</script><img src=x onerror=alert(1)>'
    frame = pd.DataFrame({'sale_date': [payload], 'total_price': [1]})
    html = generate_html_report(KPIResult(1, 1, 1, 1), {}, frame)
    assert payload not in html
    assert '&lt;/script&gt;&lt;img' in html
    encoded = re.search(r'const revenueLabels = (.*);', html).group(1)
    assert json.loads(encoded) == [payload]
    assert '<' not in encoded


@pytest.mark.parametrize('stage', ['create', 'write', 'flush', 'fsync'])
def test_atomic_io_errors_preserve_existing_destination(tmp_path, monkeypatch, stage):
    import services.services as module
    target = tmp_path / 'existing.md'
    target.write_text('OLD')
    if stage == 'fsync':
        monkeypatch.setattr(module.os, 'fsync', lambda *args: (_ for _ in ()).throw(OSError('disk error')))
    else:
        original = module.tempfile.NamedTemporaryFile
        def temporary(*args, **kwargs):
            if stage == 'create':
                raise PermissionError('cannot create temporary file')
            delegate = original(*args, **kwargs)
            class Stream:
                name = delegate.name
                def __enter__(self):
                    delegate.__enter__()
                    return self
                def __exit__(self, *exc):
                    return delegate.__exit__(*exc)
                def write(self, data):
                    if stage == 'write':
                        delegate.write(data[:2])
                        raise OSError('partial write')
                    return delegate.write(data)
                def flush(self):
                    if stage == 'flush':
                        raise OSError('flush failed')
                    return delegate.flush()
                def fileno(self):
                    return delegate.fileno()
            return Stream()
        monkeypatch.setattr(module.tempfile, 'NamedTemporaryFile', temporary)
    with pytest.raises(OSError):
        atomic_write(target, b'NEW CONTENT')
    assert target.read_text() == 'OLD'
    assert list(tmp_path.iterdir()) == [target]
