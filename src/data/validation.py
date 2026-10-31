"""Shared, non-destructive validation for both ingestion entry points."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
import re

import numpy as np
import pandas as pd


class DataValidationError(ValueError):
    """The entire candidate dataset is rejected; no rows are silently dropped."""


def normalize_columns(columns) -> list[str]:
    names = [str(c).strip().lower() for c in columns]
    duplicates = [name for name, count in Counter(names).items() if count > 1]
    if duplicates:
        raise DataValidationError(f"Duplicate normalized column names: {duplicates}")
    if any(not name for name in names):
        raise DataValidationError("Empty column name")
    return names


def validate_schema(columns) -> list[str]:
    names = normalize_columns(columns)
    missing = {'sale_date', 'customer_id', 'category'} - set(names)
    if missing:
        raise DataValidationError(f"Missing required columns: {sorted(missing)}")
    if 'total_price' not in names and not {'quantity', 'unit_price'} <= set(names):
        raise DataValidationError("Provide total_price or both quantity and unit_price")
    return names


_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?)?$')


def parse_sale_date(value, *, require_ns: bool = True) -> pd.Timestamp:
    """Only naive ISO calendar dates/timestamps; never guess locale or timezone."""
    if value is None or pd.isna(value):
        raise ValueError('missing date')
    if isinstance(value, str):
        value = value.strip()
        if not _DATE.fullmatch(value):
            raise ValueError('unsupported date/time format; use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS[.fffffffff], without timezone')
    elif not isinstance(value, (datetime, date, pd.Timestamp, np.datetime64)):
        raise ValueError('date must be ISO text or a date/datetime value')
    try:
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is not None:
            raise ValueError('timezone-aware dates are not supported')
        if pd.isna(stamp):
            raise ValueError('missing date')
        return stamp.as_unit('ns') if require_ns else stamp
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'Invalid or unsupported date/time: {value!r}: {exc}') from exc


def _rows(mask) -> str:
    # Positions are independent of a duplicated/custom DataFrame index.
    positions = np.flatnonzero(np.asarray(mask)) + 1
    shown = ', '.join(map(str, positions[:20]))
    return f"data row(s) {shown}" + (f" (first 20 of {len(positions)})" if len(positions) > 20 else '')


def validate_sales_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        raise DataValidationError('Expected a pandas DataFrame')
    result = df.copy(deep=True)
    result.columns = validate_schema(result.columns)
    errors = []
    for col in result.columns:
        if col in {'category', 'id'} or col.endswith('_id'):
            values = result[col]
            invalid = values.isna() | values.map(lambda x: isinstance(x, str) and not x.strip())
            if invalid.any():
                errors.append(f'{col}: missing/blank identifier or category at {_rows(invalid)}')
            else:
                # Do not strip/normalize identifiers: spaces and leading zeroes are data.
                result[col] = values.map(str)

    dates = []
    for pos, value in enumerate(result['sale_date'], 1):
        try:
            dates.append(parse_sale_date(value))
        except (ValueError, TypeError) as exc:
            if len(errors) < 30:
                errors.append(f'sale_date: data row {pos}: {exc}')
    if len(dates) == len(result):
        result['sale_date'] = pd.Series(dates, index=result.index, dtype='datetime64[ns]')

    for col in ('quantity', 'unit_price', 'total_price'):
        if col not in result:
            continue
        values = result[col]
        boolean = values.map(lambda x: isinstance(x, (bool, np.bool_, complex, date, np.datetime64, pd.Timedelta)))
        converted = pd.to_numeric(values.mask(boolean), errors='coerce')
        try:
            numeric = converted.astype('float64')
            invalid = boolean | ~np.isfinite(numeric)
        except (ValueError, TypeError, OverflowError):
            invalid = pd.Series(True, index=values.index)
        if invalid.any():
            errors.append(f'{col}: invalid number, missing value or infinity at {_rows(invalid)}')
        else:
            result[col] = numeric
    if errors:
        raise DataValidationError('Dataset rejected (no rows imported):\n' + '\n'.join(errors))
    if 'total_price' not in result:
        with np.errstate(over='ignore', invalid='ignore'):
            result['total_price'] = result['quantity'] * result['unit_price']
        invalid = ~np.isfinite(result['total_price'])
        if invalid.any():
            raise DataValidationError(f'total_price: multiplication overflow at {_rows(invalid)}')
    return result
