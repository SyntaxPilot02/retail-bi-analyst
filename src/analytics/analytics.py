"""
    Business Analyst: KPI and RFM
"""

# enable postponed evaluation of annotations
from __future__ import annotations
# import dataclass decorator for clean data structures
from dataclasses import dataclass
# import Dict type annotation
from typing import Dict
# import pandas library
import pandas as pd
# import datetime type for working with timestamps
from datetime import datetime


# mark class as a dataclass to auto-generate __init__, __repr__, and comparison methods
@dataclass
class KPIResult:
    # total revenue generated across transactions
    total_revenue: float
    # average revenue generated per single transaction (average bill/order value)
    avg_ticket: float
    # total number of processed transactions
    transactions_count: int
    # count of distinct customers who placed orders
    unique_customers: int


@dataclass
class RFMScores:
    # number of days elapsed since the customer's last purchase
    recency_days: int
    # total number of purchases made by the customer
    frequency: int
    # total monetary amount spent by the customer
    monetary: float
    # segment label assigned based on RFM rules (e.g 'Best', 'Loyal', 'At risk', 'Regular')
    segment: str


# function to calculate basic Key Performance Indicators (KPIs) from sales data
def calculate_kpi_results(df: pd.DataFrame) -> KPIResult:
    """
        Calculate basic KPI metrics
    """
    # check if the DataFrame is empty; returned zeroed KPI metrics if true
    if df.empty:
        return KPIResult(0.0, 0.0, 0, 0)

    # calculate total revenue by summing up the 'total_price' column and casting to float
    total_revenue = float(df["total_price"].sum())
    # count the total number of transaction records (rows in DataFrame)
    transactions_count = int(df.shape[0])
    # count unique customer IDs present in the dataset
    unique_customers = int(df["customer_id"].nunique())
    # calculate average ticket size; guard against division by zero if transactions_count is 0
    avg_ticket = total_revenue / transactions_count if transactions_count > 0 else 0.0

    # return structured object containing calculated KPI values
    return KPIResult(
        total_revenue=total_revenue,
        avg_ticket=avg_ticket,
        transactions_count=transactions_count,
        unique_customers=unique_customers,
    )

# function to perform RFM (Recency, Frequency, Monetary) analysis on customer transactions
def calculate_rfm_results(df: pd.DataFrame, ref_date: datetime | None = None) -> Dict[str, RFMScores]:
    """
        Calculate RFM metrics
    """
    # return empty dictionary if the provided DataFrame contains no data
    if df.empty:
        return dict()

    # if reference date for recency calculation is not specified, use the maximum sale date in dataset
    if ref_date is None:
        ref_date = df["sale_date"].max()

    # group sales dataset by customer ID
    grouped = df.groupby("customer_id")
    # initialize dictionary to store RFM metrics per customer ID string
    results: Dict[str, RFMScores] = dict()

    # iterate over each customer ID and their corresponding subgroup of transactions
    for cid, group in grouped:
        # find the latest sale date for the current customer
        last_purchase = group["sale_date"].max()
        # calculate recency in full days relative to the reference date
        recency_days = (ref_date - last_purchase).days
        # frequency is measured as total number of transactions by the customer
        frequency = group.shape[0]
        # monetary is measured as total spend across all customer transactions
        monetary = float(group["total_price"].sum())

        # RFM Segmentation
        if recency_days <= 30 and frequency >= 5 and monetary >= 1000:
            segment = "Best"
        elif recency_days <= 90 and frequency >= 3:
            segment = "Loyal"
        elif recency_days > 180:
            segment = "At risk"
        else:
            segment = "Regular"

        # map customer ID string to their computed RFMScores dataclass instance
        results[str(cid)] = RFMScores(
            recency_days=recency_days,
            frequency=frequency,
            monetary=monetary,
            segment=segment,
        )

    # return dictionary of customer RFM results
    return results