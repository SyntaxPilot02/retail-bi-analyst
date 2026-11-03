"""CSV and read-only SQLite ingestion. No silent row cleanup."""
from __future__ import annotations

import csv
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from src.data.validation import validate_schema, validate_sales_dataframe


@dataclass
class DataSourceConfig:
    source_type: str
    path: Path
    table_name: Optional[str] = None


class DataLoader:
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config

    def load_data(self) -> pd.DataFrame:
        if self.config.source_type == 'csv':
            return self._load_from_csv()
        if self.config.source_type == 'sqlite':
            return self._load_from_sqlite()
        raise ValueError(f'Unknown source type: {self.config.source_type}')

    def _load_from_csv(self) -> pd.DataFrame:
        # Check the original header BEFORE pandas can mangle duplicate names.
        # Read body with csv too: pandas can silently reinterpret surplus fields as an index.
        with Path(self.config.path).open('r', encoding='utf-8-sig', newline='') as stream:
            reader = csv.reader(stream, strict=True)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise ValueError('CSV file is empty') from exc
            names = validate_schema(header)
            rows = []
            for row in reader:
                if len(row) != len(header):
                    raise ValueError(f'CSV line {reader.line_num}: expected {len(header)} fields, got {len(row)}')
                rows.append(row)
        # All input text is preserved, including 0001 and literal identifiers such as NA.
        return validate_sales_dataframe(pd.DataFrame(rows, columns=names))

    def _load_from_sqlite(self) -> pd.DataFrame:
        path = Path(self.config.path).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError('SQLite path must be an existing file')
        name = self.config.table_name
        if not isinstance(name, str) or not name:
            raise ValueError('No table name provided')
        # Path.as_uri percent-escapes ?, #, spaces etc.; mode=ro never creates a file.
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
            conn.execute('PRAGMA query_only = ON')
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if name not in tables:
                raise ValueError(f'Table {name!r} not found; available tables: {sorted(tables)!r}')
            quoted_name = '"' + name.replace('"', '""') + '"'
            cursor = conn.execute(f'SELECT * FROM {quoted_name}')
            columns = validate_schema([description[0] for description in cursor.description])
            df = pd.DataFrame.from_records(cursor.fetchall(), columns=columns)
        return validate_sales_dataframe(df)
