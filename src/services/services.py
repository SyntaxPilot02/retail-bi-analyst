"""GUI-independent use cases. A candidate is fully prepared before publication."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os
import tempfile
import numpy as np
import pandas as pd
from src.analytics.analytics import KPIResult, RFMScores, calculate_kpi_results, calculate_rfm_results
from src.data.data_loader import DataLoader, DataSourceConfig
from src.data.repository import SalesRepository, SalesFilter
from src.reports.report_generator import generate_markdown_report, generate_html_report


@dataclass(frozen=True)
class PreparedState:
    repo: SalesRepository
    active_filter: Optional[SalesFilter]
    frame: pd.DataFrame
    kpi: KPIResult
    rfm: dict[str, RFMScores]
    markdown: str
    categories: list[str]
    customers: list[str]
    date_min: Optional[pd.Timestamp]
    date_max: Optional[pd.Timestamp]


class AnalysisService:
    def prepare_import(self, config: DataSourceConfig) -> PreparedState:
        repo = SalesRepository(DataLoader(config).load_data())
        return self.prepare(repo, None)

    def prepare(self, repo: SalesRepository, flt: Optional[SalesFilter]) -> PreparedState:
        raw = repo.raw
        frame = repo.filtered(flt) if flt is not None else raw.copy(deep=True)
        with np.errstate(over='ignore', invalid='ignore'):
            kpi = calculate_kpi_results(frame)
            rfm = calculate_rfm_results(frame)
        # Finite inputs can still overflow during aggregation. Never publish infinity.
        monetary = [kpi.total_revenue, kpi.avg_ticket] + [s.monetary for s in rfm.values()]
        if not all(np.isfinite(v) for v in monetary):
            raise ValueError('Numeric overflow in KPI/RFM aggregation')
        for key in ('sale_date', 'category'):
            with np.errstate(over='ignore', invalid='ignore'):
                totals = frame.groupby(key)['total_price'].sum().to_numpy()
            if not np.isfinite(totals).all():
                raise ValueError(f'Numeric overflow in {key} aggregation')
        markdown = generate_markdown_report(kpi, rfm)
        return PreparedState(repo, flt, frame, kpi, rfm, markdown,
                             repo.unique_categories(), repo.unique_customers(),
                             None if raw.empty else raw['sale_date'].min(),
                             None if raw.empty else raw['sale_date'].max())

    def export_report(self, repo: SalesRepository, flt: Optional[SalesFilter], path: Path, html: bool = False) -> Path:
        state = self.prepare(repo, flt)
        if html and state.frame.empty:
            raise ValueError('No rows available for HTML report')
        content = generate_html_report(state.kpi, state.rfm, state.frame) if html else state.markdown
        atomic_write(path, content.encode('utf-8'))
        return path


def atomic_write(path: Path, content: bytes) -> None:
    """Same-directory temporary file + replace: failure preserves the old destination."""
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
