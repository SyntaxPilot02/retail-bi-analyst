"""Validated sales repository with calendar-day filtering."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
from data.validation import parse_sale_date, validate_sales_dataframe


@dataclass
class SalesFilter:
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    category: Optional[str] = None
    customer_id: Optional[str] = None


class SalesRepository:
    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df.copy(deep=True)
        self._prepare_dataframe()

    def _prepare_dataframe(self) -> None:
        self._df = validate_sales_dataframe(self._df)

    @property
    def raw(self) -> pd.DataFrame:
        return self._df.copy(deep=True)

    def filtered(self, flt: SalesFilter) -> pd.DataFrame:
        start = datetime.combine(parse_sale_date(flt.date_from, require_ns=False).date(), datetime.min.time()) if flt.date_from is not None else None
        end = datetime.combine(parse_sale_date(flt.date_to, require_ns=False).date(), datetime.min.time()) if flt.date_to is not None else None
        if start is not None and end is not None and start > end:
            raise ValueError('Start date must not be later than end date')
        df = self._df
        if start is not None:
            df = df[df['sale_date'] >= start]
        if end is not None:
            try:
                exclusive_end = end + timedelta(days=1)
            except (ValueError, OverflowError) as exc:
                raise ValueError('End date is outside the supported calendar range') from exc
            df = df[df['sale_date'] < exclusive_end]
        if flt.category is not None:
            df = df[df['category'] == flt.category]
        if flt.customer_id is not None:
            df = df[df['customer_id'] == flt.customer_id]
        return df.copy(deep=True)

    def unique_categories(self) -> list[str]:
        return sorted(self._df['category'].unique().tolist())

    def unique_customers(self) -> list[str]:
        return sorted(self._df['customer_id'].unique().tolist())
