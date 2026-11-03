"""
Graph building utilities for the Retail BI Analyst application.
"""

# enable postponed evaluation of annotations
from __future__ import annotations

# import Dict and Tuple type and cast function for strict typing helpers
from typing import Dict, Tuple
# import datetime type for working with timestamps
from datetime import datetime

# import pandas library
import pandas as pd
# import Matplotlib Axes type annotation for plotting target control
from matplotlib.axes import Axes

# import RFM calculator function to build segment distribution visualizer
from src.analytics.analytics import calculate_rfm_results


# constant choices for graph data source topics
class GraphDataChoice:
    REVENUE_BY_DATE = "Revenue by date"
    REVENUE_BY_CATEGORY = "Revenue by category"
    CUSTOMERS_BY_SEGMENT = "Customers by segment"


# constant choices for chart visualization types
class GraphType:
    LINE = "Line"
    BAR = "Bar"
    PIE = "Pie"


# main dispatcher function to generate charts on Matplotlib axes
def build_graph(
    df: pd.DataFrame,
    data_choice: str,
    chart_type: str,
    ax: Axes,
) -> None:
    """
    Build a graph on the given matplotlib Axes based on the
    selected data and chart type.

    Raises ValueError with a human-readable message when the
    requested visualization is not possible.
    """
    # guard against invalid or empty input DataFrame
    if df is None or df.empty:
        raise ValueError("No data available for visualization")

    # clear previous drawing and axis states from the target Matplotlib subplot
    ax.clear()

    # route visualization logic according to user's selected matric topic
    if data_choice == GraphDataChoice.REVENUE_BY_DATE:
        _build_revenue_by_date(df, chart_type, ax)
    elif data_choice == GraphDataChoice.REVENUE_BY_CATEGORY:
        _build_revenue_by_category(df, chart_type, ax)
    elif data_choice == GraphDataChoice.CUSTOMERS_BY_SEGMENT:
        _build_customers_by_segment(df, chart_type, ax)
    else:
        # throw exception for unrecognized dataset options
        raise ValueError(f"Unknown data choice: {data_choice}")


# helper function to extract and aggregate revenue aggregated by date
def _prepare_revenue_series(df: pd.DataFrame) -> Tuple[list[str], list[float]]:
    # validate presence of necessary columns in the DataFrame
    if "sale_date" not in df.columns or "total_price" not in df.columns:
        raise ValueError("Columns 'sale_date' and 'total_price' are required")

    # group total by sale date and sort chronologically
    series = df.groupby("sale_date")["total_price"].sum().sort_index()
    # format dates to standard YYYY-MM-DD strings for plotting labels
    labels = [
        d.strftime("%Y-%m-%d") if isinstance(d, datetime) else str(d)
        for d in series.index
    ]
    # extract calculated revenue numerical values
    values = [float(v) for v in series.values]

    # guard against empty calculation output
    if not labels:
        raise ValueError("No data points for revenue by date")

    # return formatted label list and value list tuple
    return labels, values


# helper function to render revenue by date chart onto given Matplotlib axes
def _build_revenue_by_date(df: pd.DataFrame, chart_type: str, ax: Axes) -> None:
    # retrieve prepared label strings and numeric values
    labels, values = _prepare_revenue_series(df)

    # plot line chart with point markers
    if chart_type == GraphType.LINE:
        ax.plot(labels, values, marker="o", color="#38bdf8")
    # plot bar chart
    elif chart_type == GraphType.BAR:
        ax.bar(labels, values, color="#3b82f6")
    # disallow pie chart representation for time-series data
    elif chart_type == GraphType.PIE:
        raise ValueError("Pie chart is not appropriate for time-series revenue")
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")

    # set chart title
    ax.set_title("Revenue by date")
    # set x-axis title label
    ax.set_xlabel("Date")
    # set y-axis title label
    ax.set_ylabel("Revenue")
    # rotate x-axis tick labels for readability
    ax.tick_params(axis="x", rotation=45)


# helper function to aggregate total revenue by product categories
def _prepare_category_series(df: pd.DataFrame) -> Tuple[list[str], list[float]]:
    # verify mandatory column availability
    if "category" not in df.columns or "total_price" not in df.columns:
        raise ValueError("Columns 'category' and 'total_price' are required")

    # group revenue by category and sort in descending order
    series = df.groupby("category")["total_price"].sum().sort_values(ascending=False)
    # extract category names as labels list
    labels = list(series.index)
    # convert numerical revenue values to float list
    values = [float(v) for v in series.values]

    # guard against empty category lists
    if not labels:
        raise ValueError("No data points for revenue by category")

    # return category labels and total values
    return labels, values


# helper function to render revenue by product category chart
def _build_revenue_by_category(df: pd.DataFrame, chart_type: str, ax: Axes) -> None:
    # retrieve prepared label strings and numeric values
    labels, values = _prepare_category_series(df)

    # plot categorical bar chart
    if chart_type == GraphType.BAR:
        ax.bar(labels, values, color="#3b82f6")
    # plot pie chart with percentage formatting
    elif chart_type == GraphType.PIE:
        ax.pie(values, labels=labels, autopct="%1.1f%%")
    # disallow line chart representation for unordered discrete categories
    elif chart_type == GraphType.LINE:
        raise ValueError("Line chart is not ideal for categorical revenue; use bar or pie")
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")

    # set chart title
    ax.set_title("Revenue by category")
    # configure axes labels only for non-pie chart types
    if chart_type != GraphType.PIE:
        ax.set_xlabel("Category")
        ax.set_ylabel("Revenue")
        ax.tick_params(axis="x", rotation=45)


# helper function to count customer quantities per RFM segment
def _prepare_segment_counts(df: pd.DataFrame) -> Dict[str, int]:
    # compute RFM metrics dictionary
    rfm = calculate_rfm_results(df)
    # validate that RFM data was successfully evaluated
    if not rfm:
        raise ValueError("No RFM data available for this dataset")

    # initialize counter dictionary for segments
    segment_counts: Dict[str, int] = {}
    # aggregate customer count per segment type
    for scores in rfm.values():
        segment_counts[scores.segment] = segment_counts.get(scores.segment, 0) + 1

    # return dictionary mapping segment names to customer counts
    return segment_counts


# helper function to render customer RFM segment distribution chart
def _build_customers_by_segment(df: pd.DataFrame, chart_type: str, ax: Axes) -> None:
    # obtain segment count map
    segment_counts = _prepare_segment_counts(df)
    # extract segment labels list
    labels = list(segment_counts.keys())
    # extract segment customer counts list
    values = list(segment_counts.values())

    # draw bar chart for RFM segment counts
    if chart_type == GraphType.BAR:
        ax.bar(labels, values, color="#22c55e")
    # draw pie chart displaying segment proportions
    elif chart_type == GraphType.PIE:
        ax.pie(values, labels=labels, autopct="%1.1f%%")
    # draw line chart showing segment counts
    elif chart_type == GraphType.LINE:
        ax.plot(labels, values, marker="o", color="#22c55e")
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")

    # set chart header title
    ax.set_title("Customers by segment (RFM)")
    # apply axis descriptions for non-pie charts
    if chart_type != GraphType.PIE:
        ax.set_xlabel("Segment")
        ax.set_ylabel("Customers")