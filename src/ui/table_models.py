"""Read-only Qt models; raw sort values are independent of display strings."""
from datetime import datetime, date
from numbers import Real, Integral
import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel

SORT_ROLE = Qt.ItemDataRole.UserRole + 1


def _item(value, display=None):
    if isinstance(value, (pd.Timestamp, datetime, date)):
        stamp = pd.Timestamp(value)
        raw = int(stamp.value)  # nanoseconds; unlike formatted strings, lossless and chronological
    elif isinstance(value, Integral):
        raw = int(value)
    elif isinstance(value, Real):
        raw = float(value)
    else:
        raw = str(value)
    item = QStandardItem(str(value) if display is None else display)
    item.setData(raw, SORT_ROLE)
    item.setEditable(False)
    item.setTextAlignment((Qt.AlignmentFlag.AlignRight if isinstance(value, Real) else Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignVCenter)
    return item


def make_model(headers, rows, displays=None):
    rows = list(rows)
    model = QStandardItemModel(len(rows), len(headers))
    model.setHorizontalHeaderLabels(list(headers))
    model.setSortRole(SORT_ROLE)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            model.setItem(r, c, _item(value, None if displays is None else displays[r][c]))
    return model


def data_model(df):
    return make_model(df.columns, df.itertuples(index=False, name=None))


def kpi_model(kpi):
    rows = [('Total Revenue', kpi.total_revenue), ('Average Bill', kpi.avg_ticket),
            ('Transactions', kpi.transactions_count), ('Unique Customers', kpi.unique_customers)]
    displays = [[name, f'{value:,.2f}' if i < 2 else str(value)] for i, (name, value) in enumerate(rows)]
    return make_model(['Metric', 'Value'], rows, displays)


def rfm_model(rfm):
    rows = [(cid, s.recency_days, s.frequency, s.monetary, s.segment) for cid, s in rfm.items()]
    displays = [[str(cid), str(recency), str(freq), f'{money:,.2f}', segment] for cid, recency, freq, money, segment in rows]
    return make_model(['Customer', 'Recency (days)', 'Frequency', 'Monetary', 'Segment'], rows, displays)
