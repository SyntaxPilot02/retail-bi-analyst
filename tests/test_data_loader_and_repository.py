from datetime import datetime
import sqlite3
import numpy as np
import pandas as pd
import pytest
from data.data_loader import DataLoader, DataSourceConfig
from data.repository import SalesRepository, SalesFilter
from data.validation import DataValidationError


@pytest.mark.parametrize('column', ['sale_date', 'customer_id', 'category', 'unit_price'])
def test_missing_schema(sales, column):
    with pytest.raises(DataValidationError, match='Missing|required|Provide'):
        SalesRepository(sales.drop(columns=column))


@pytest.mark.parametrize('columns', [['customer_id', 'customer_id'], [' Customer_ID ', 'customer_id']])
def test_duplicate_raw_csv_headers(tmp_path, columns):
    path = tmp_path / 'duplicate.csv'
    path.write_text('sale_date,category,total_price,' + ','.join(columns) + '\n2025-01-01,A,1,001,002\n')
    with pytest.raises(DataValidationError, match='Duplicate'):
        DataLoader(DataSourceConfig('csv', path)).load_data()


def test_duplicate_repository_headers(sales):
    sales[' Category '] = sales.category
    with pytest.raises(DataValidationError, match='Duplicate'):
        SalesRepository(sales)


@pytest.mark.parametrize('field,value', [
    ('sale_date', '2025-02-30'), ('sale_date', '02/03/2025'), ('sale_date', '2025-01-01T12:00:00Z'),
    ('sale_date', '2025-01-01T12:00:00+02:00'), ('sale_date', 20250101), ('sale_date', None),
    ('sale_date', pd.Timestamp('2025-01-01', tz='UTC')),
    ('quantity', 'two'), ('quantity', ''), ('quantity', None), ('quantity', np.inf),
    ('unit_price', -np.inf), ('unit_price', 'NaN'), ('unit_price', True),
    ('customer_id', ''), ('customer_id', None), ('category', '  '),
])
def test_invalid_cells_reject_dataset(sales, field, value):
    sales.loc[1, field] = value
    with pytest.raises(DataValidationError, match=field) as exc:
        SalesRepository(sales)
    assert 'row' in str(exc.value)
    assert '2' in str(exc.value)


@pytest.mark.parametrize('value', [None, '', 'bad', np.inf, -np.inf])
def test_existing_total_is_not_filled(sales, value):
    sales['total_price'] = ['1', value, '3', '4']
    with pytest.raises(DataValidationError, match='total_price'):
        SalesRepository(sales)


def test_checked_total_and_identifiers(csv_config):
    frame = DataLoader(csv_config).load_data()
    assert frame.customer_id.tolist() == ['0001', '0010', '0001', 'NA']
    assert frame.total_price.tolist() == [10, 20, 3, 3]
    assert pd.api.types.is_datetime64_ns_dtype(frame.sale_date)


def test_all_identifier_columns_preserve_zeroes(tmp_path):
    path = tmp_path / 'ids.csv'
    path.write_text('sale_date,customer_id,product_id,transaction_id,category,total_price\n2025-01-01,0001,0002,0003,A,10\n')
    row = DataLoader(DataSourceConfig('csv', path)).load_data().iloc[0]
    assert (row.customer_id, row.product_id, row.transaction_id) == ('0001', '0002', '0003')


def test_multiply_overflow(sales):
    sales.loc[0, ['quantity', 'unit_price']] = ['1e308', '1e308']
    with pytest.raises(DataValidationError, match='overflow'):
        SalesRepository(sales)


def test_repository_copy_isolation(sales):
    repo = SalesRepository(sales)
    result = repo.raw
    result.loc[0, 'total_price'] = -123
    assert repo.raw.iloc[0].total_price == 10


def test_calendar_end_and_reverse(sales):
    repo = SalesRepository(sales)
    frame = repo.filtered(SalesFilter(datetime(2025, 1, 2), datetime(2025, 1, 2)))
    assert len(frame) == 2
    assert frame.sale_date.max().nanosecond == 999
    with pytest.raises(ValueError, match='later'):
        repo.filtered(SalesFilter(datetime(2025, 1, 3), datetime(2025, 1, 1)))


def test_unsupported_filter_datetime(sales):
    repo = SalesRepository(sales)
    for value in ('01/02/2025', '2025-01-01T00:00:00Z', 20250101):
        with pytest.raises(ValueError):
            repo.filtered(SalesFilter(date_to=value))


def test_malformed_csv_row(tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text('sale_date,customer_id,category,total_price\n2025-01-01,001,A,10,EXTRA\n')
    with pytest.raises(ValueError, match='expected 4 fields'):
        DataLoader(DataSourceConfig('csv', path)).load_data()


@pytest.mark.parametrize('name', ['sales', 'sales items', 'x"; DROP TABLE sales;--', 'x"y', ' spaced '])
def test_sqlite_valid_quoted_names(tmp_path, name):
    path = tmp_path / 'a # ?.sqlite'
    quoted = '"' + name.replace('"', '""') + '"'
    with sqlite3.connect(path) as conn:
        conn.execute(f'CREATE TABLE {quoted} (sale_date TEXT, customer_id TEXT, category TEXT, total_price REAL)')
        conn.execute(f'INSERT INTO {quoted} VALUES (?, ?, ?, ?)', ('2025-01-01', '0001', 'A', 2))
    frame = DataLoader(DataSourceConfig('sqlite', path, name)).load_data()
    assert frame.customer_id.iloc[0] == '0001'
    assert frame.total_price.iloc[0] == 2


def test_sqlite_injection_rejected(tmp_path):
    path = tmp_path / 'sales.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE sales (value TEXT)')
    with pytest.raises(ValueError, match='not found'):
        DataLoader(DataSourceConfig('sqlite', path, 'sales; DROP TABLE sales;--')).load_data()
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT count(*) FROM sales').fetchone()[0] == 0


def test_sqlite_missing_is_not_created(tmp_path):
    path = tmp_path / 'missing.db'
    with pytest.raises(FileNotFoundError):
        DataLoader(DataSourceConfig('sqlite', path, 'sales')).load_data()
    assert not path.exists()


def test_sqlite_readonly_and_connection_closed(tmp_path, monkeypatch):
    import data.data_loader as module
    path = tmp_path / 'sales.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE sales (sale_date TEXT, customer_id TEXT, category TEXT, total_price REAL)')
        conn.execute("INSERT INTO sales VALUES ('2025-01-01', '0001', 'A', 1)")
    original = sqlite3.connect
    connections = []
    def connect(*args, **kwargs):
        assert args[0].endswith('?mode=ro') and kwargs['uri'] is True
        conn = original(*args, **kwargs)
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            conn.execute('CREATE TABLE forbidden (x)')
        connections.append(conn)
        return conn
    monkeypatch.setattr(module.sqlite3, 'connect', connect)
    DataLoader(DataSourceConfig('sqlite', path, 'sales')).load_data()
    with pytest.raises(ValueError):
        DataLoader(DataSourceConfig('sqlite', path, 'missing')).load_data()
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            conn.execute('SELECT 1')


@pytest.mark.parametrize('stamp,day', [
    ('2262-04-11 23:47:16.854775807', '2262-04-11'),
    ('1677-09-21 00:12:43.145224193', '1677-09-21'),
])
def test_supported_timestamp_extremes_include_whole_last_day(stamp, day):
    frame = pd.DataFrame({'sale_date': [stamp], 'customer_id': ['001'], 'category': ['A'], 'total_price': [1]})
    result = SalesRepository(frame).filtered(SalesFilter(date_from=day, date_to=day))
    assert len(result) == 1


def test_csv_normalized_headers_and_no_mutation(tmp_path):
    path = tmp_path / 'headers.csv'
    path.write_text(' Sale_Date , CUSTOMER_ID , Category , TOTAL_PRICE \n2025-01-01,0001,A,12.5\n')
    frame = DataLoader(DataSourceConfig('csv', path)).load_data()
    assert frame.columns.tolist() == ['sale_date', 'customer_id', 'category', 'total_price']
    assert frame.customer_id.iloc[0] == '0001'


def test_empty_file_vs_empty_dataset(tmp_path):
    path = tmp_path / 'empty.csv'
    path.write_text('')
    with pytest.raises(ValueError, match='empty'):
        DataLoader(DataSourceConfig('csv', path)).load_data()
    path.write_text('sale_date,customer_id,category,total_price\n')
    assert DataLoader(DataSourceConfig('csv', path)).load_data().empty


@pytest.mark.parametrize('value', [pd.Timestamp('2025-01-01'), datetime(2025, 1, 1), pd.Timedelta(days=1), complex(1, 2)])
def test_dates_and_complex_are_not_numeric_sales(sales, value):
    sales.loc[0, 'quantity'] = value
    with pytest.raises(DataValidationError, match='quantity'):
        SalesRepository(sales)


def test_sqlite_normalized_duplicates_reject_and_close(tmp_path, monkeypatch):
    import data.data_loader as module
    path = tmp_path / 'duplicate.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE sales (sale_date TEXT, customer_id TEXT, category TEXT, " category " TEXT, total_price REAL)')
    original = sqlite3.connect
    connections = []
    def connect(*args, **kwargs):
        conn = original(*args, **kwargs)
        connections.append(conn)
        return conn
    monkeypatch.setattr(module.sqlite3, 'connect', connect)
    with pytest.raises(DataValidationError, match='Duplicate'):
        DataLoader(DataSourceConfig('sqlite', path, 'sales')).load_data()
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        connections[0].execute('SELECT 1')


@pytest.mark.parametrize('stamp', ['2025-01-01', '2025-01-01T12:34:56', '2025-01-01 12:34:56.123456789', datetime(2025, 1, 1, 12, 34, 56)])
def test_supported_naive_dates(sales, stamp):
    sales.loc[0, 'sale_date'] = stamp
    assert len(SalesRepository(sales).raw) == 4
