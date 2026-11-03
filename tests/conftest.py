import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_API', 'pyside6')
import pandas as pd
import pytest
from src.data.data_loader import DataSourceConfig


@pytest.fixture
def sales():
    return pd.DataFrame({
        'sale_date': ['2025-01-01', '2025-01-02 12:30:00', '2025-01-02 23:59:59.999999999', '2025-01-03'],
        'customer_id': ['0001', '0010', '0001', 'NA'],
        'category': ['A', 'B', 'A', 'B'],
        'quantity': ['2', '10', '1', '3'],
        'unit_price': ['5', '2', '3', '1'],
    })


@pytest.fixture
def csv_config(tmp_path, sales):
    path = tmp_path / 'sales.csv'
    sales.to_csv(path, index=False)
    return DataSourceConfig('csv', path)
