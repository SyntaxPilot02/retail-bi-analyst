"""
    Text and HTML report generator
"""

# enable postponed evaluation of annotations
from __future__ import annotations

# import Dict and Tuple type and cast function for strict typing helpers
from typing import Dict, List
# import datetime type for working with timestamps
from datetime import datetime
# import json
# Serialize data for inline JavaScript
import json
from html import escape

# import pandas library
import pandas as pd

# import analytics dataclasses
from src.analytics.analytics import KPIResult, RFMScores


def _markdown_cell(value) -> str:
    # Encode pipe rather than backslash-escape: even malicious backslashes stay harmless.
    text = escape(str(value), quote=True).replace("\r\n", "\n").replace("\r", "\n")
    for char in "\\`*_[]":
        text = text.replace(char, f"&#{ord(char)};")
    return text.replace("|", "&#124;").replace("\n", "<br>")


def _script_json(value) -> str:
    text = json.dumps(value, ensure_ascii=True, allow_nan=False)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


# function to generate Markdown formatted analytical executive summary report
def generate_markdown_report(kpi: KPIResult, rfm: Dict[str, RFMScores]) -> str:
    """
    Generate markdown report from metrics.
    """
    # initialize empty line for text assembly
    lines: list[str] = []

    # append document header
    lines.append("# Sales report")
    lines.append("")

    # append KPI summary section header
    lines.append("## Basic metrics (KPI)")

    # format and append Key Performance Indicator bullet points
    lines.append(f"- Total revenue: **{kpi.total_revenue:,.2f}**")
    lines.append(f"- Average bill: **{kpi.avg_ticket:,.2f}**")
    lines.append(f"- Transactions counter: **{kpi.transactions_count}**")
    lines.append(f"- Unique customers: **{kpi.unique_customers}**")
    lines.append("")

    # append RFM Analysis table section header
    lines.append("## RFM-analysis metrics")
    lines.append("")

    # construct Markdown table header row
    lines.append("| Customer | Recency (days) | Frequency | Monetary | Segment |")
    # construct Markdown table alignment delimiter
    lines.append("| -------- | -------------- | --------- | -------- | ------- |")

    # iterate over customer and construct tabular detail rows
    for cid, scores in rfm.items():
        lines.append(
            f"| {_markdown_cell(cid)} | {_markdown_cell(scores.recency_days)} | {_markdown_cell(scores.frequency)} | "
            f"{scores.monetary:,.2f} | {_markdown_cell(scores.segment)} |"
        )
    lines.append("")

    # append insights and recommendations header
    lines.append("## Conclusions and recommendations")
    lines.append("")

    # calculate total customer count evaluated in RFM analysis
    total_customers = len(rfm)
    # check if dataset contains insufficient metrics for deep business insights
    if total_customers == 0 or kpi.transactions_count == 0 or kpi.total_revenue == 0:
        lines.append(
            "- The current dataset does not contain enough customer-level activity "
            "to support reliable segmentation. Focus on increasing data volume "
            "and observation period before drawing strategic conclusions."
        )
        # returned combined Markdown text
        return "\n".join(lines)

    # initialize segment distribution tally dictionary
    segment_counts: Dict[str, int] = {}
    for scores in rfm.values():
        segment_counts[scores.segment] = segment_counts.get(scores.segment, 0) + 1

    # retrieve individual counts for key customer segments
    best_count = segment_counts.get("Best", 0)
    loyal_count = segment_counts.get("Loyal", 0)
    at_risk_count = segment_counts.get("At risk", 0)
    regular_count = segment_counts.get("Regular", 0)

    # helper inline function to calculate percentage share of a segment
    def share(count: int) -> float:
        return (count / total_customers * 100.0) if total_customers > 0 else 0.0

    # calculate percentage shares for each segment
    best_share = share(best_count)
    loyal_share = share(loyal_count)
    at_risk_share = share(at_risk_count)
    regular_share = share(regular_count)

    # append general dataset overview summary sentence
    lines.append(
        f"- The analyzed period includes **{kpi.transactions_count}** transactions "
        f"from **{kpi.unique_customers}** unique customers, generating a total "
        f"revenue of **{kpi.total_revenue:,.2f}** and an average bill of "
        f"**{kpi.avg_ticket:,.2f}**."
    )

    # append recommendations tailored to the 'Best' customer segment if populated
    if best_count > 0:
        lines.append(
            f"- High-value buyers in the **Best** segment represent approximately "
            f"**{best_share:.0f}%** of the active customer base. This core group "
            "warrants priority service, personalized offers and early access to "
            "new products to protect its contribution to revenue."
        )

    # append warnings and advice for the 'At risk' customer segment if populated
    if at_risk_count > 0:
        lines.append(
            f"- Customers classified as **At risk** account for roughly "
            f"**{at_risk_share:.0f}%** of the base. This indicates a tangible "
            "churn exposure. Launch targeted win-back campaigns (time-limited "
            "discounts, reminder emails, reactivation bundles) to reduce "
            "potential revenue loss."
        )

    # append growth strategy recommendations for the 'Loyal' customer segment if populated
    if loyal_count > 0:
        lines.append(
            f"- The **Loyal** segment, representing about **{loyal_share:.0f}%** "
            "of customers, forms a natural pipeline into the Best segment. "
            "Structured loyalty programs, upsell paths and cross-selling of "
            "higher-margin products can systematically lift their value."
        )

    # append conversion guidance for 'Regular' customer segment if populated
    if regular_count > 0:
        lines.append(
            f"- Regular customers (~**{regular_share:.0f}%** of the base) provide "
            "broad volume but still have room for frequency and basket expansion. "
            "Use simple bundles, targeted messaging and frictionless promotions "
            "to convert part of this group into Loyal buyers."
        )

    # append strategic long-term segment tracking advice
    lines.append(
        "- Track how the distribution across Best, Loyal, Regular and At risk "
        "segments evolves over time. A shift towards Best and Loyal indicates "
        "effective retention and value management, while growth in At risk "
        "requires immediate corrective action."
    )

    # append holistic BI action recommendation
    lines.append(
        "- Combine RFM trends with product-level analytics (top categories, "
        "margins, seasonality) to adjust pricing, assortment and service design "
        "in a data-driven way, rather than relying on intuition alone."
    )

    # join lines with newlines into a single cohesive Markdown string
    return "\n".join(lines)


# function to build an interactive HTML analytical web report dashboard
def generate_html_report(
    kpi: KPIResult,
    rfm: Dict[str, RFMScores],
    df: pd.DataFrame,
) -> str:
    """
    Generate an interactive HTML report (single-page dashboard)
    using embedded data and Chart.js.

    - KPI cards at the top.
    - Line chart: revenue by date.
    - Bar chart: customers by RFM segment.
    - Embedded CSS/data and JS; the existing Chart.js CDN requires network access for charts.
    """
    # --- Prepare data for charts ---

    # extract time series daily revenue data if DataFrame contains mandatory fields
    if df is not None and not df.empty and "sale_date" in df.columns and "total_price" in df.columns:
        # group revenue sum by sale date sorted chronologically
        revenue_series = (
            df.groupby("sale_date")["total_price"].sum().sort_index()
        )
        # format dates as string for chart labels
        revenue_labels: List[str] = [
            d.strftime("%Y-%m-%d") if isinstance(d, datetime) else str(d)
            for d in revenue_series.index
        ]
        # cast value to standard float primitives
        revenue_values: List[float] = [float(v) for v in revenue_series.values]
        # retrieve latest recorded sale date string
        latest_date_str = revenue_labels[-1] if revenue_labels else ""
    else:
        # fallback to empty lists if inputs are missing
        revenue_labels = []
        revenue_values = []
        latest_date_str = ""

    # tally customer RFM segment counts
    segment_counts: Dict[str, int] = {}
    for scores in rfm.values():
        segment_counts[scores.segment] = segment_counts.get(scores.segment, 0) + 1

    # extract segment labels and quantities
    segment_labels: List[str] = list(segment_counts.keys())
    segment_values: List[int] = list(segment_counts.values())

    # convert python lists into JSON string format for direct insertion into inline JS code
    json_revenue_labels = _script_json(revenue_labels)
    json_revenue_values = _script_json(revenue_values)
    json_segment_labels = _script_json(segment_labels)
    json_segment_values = _script_json(segment_values)

    # --- Build HTML ---

    # construct complete standalone HTML page template with dynamic string interpolations
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Retail BI Analyst - Web Report</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<!-- Chart.js CDN -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1"></script>
<style>
:root {{
  --bg-main: #0f172a;
  --bg-card: #1e293b;
  --bg-surface: #020617;
  --accent: #38bdf8;
  --accent-soft: rgba(56, 189, 248, 0.15);
  --text-primary: #f9fafb;
  --text-secondary: #9ca3af;
  --positive: #22c55e;
  --negative: #ef4444;
  --radius: 12px;
  --gap: 20px;
  --shadow-soft: 0 12px 30px rgba(15, 23, 42, 0.6);
}}

body {{
  margin: 0;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: radial-gradient(circle at top left, #1e293b 0, #020617 45%, #000 100%);
  color: var(--text-primary);
}}

.dashboard-container {{
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}}

.dashboard-header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 24px;
}}

.dashboard-header h1 {{
  font-size: 28px;
  margin: 0;
}}

.dashboard-meta {{
  text-align: right;
}}

.dashboard-meta span {{
  display: block;
  font-size: 13px;
  color: var(--text-secondary);
}}

.kpi-row {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--gap);
  margin-bottom: 24px;
}}

.kpi-card {{
  background: var(--bg-card);
  border-radius: var(--radius);
  padding: 18px 20px;
  box-shadow: var(--shadow-soft);
  position: relative;
  overflow: hidden;
}}

.kpi-card::before {{
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at top right, var(--accent-soft), transparent 60%);
  opacity: 0.9;
}}

.kpi-label {{
  font-size: 13px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 6px;
}}

.kpi-value {{
  font-size: 26px;
  font-weight: 700;
  margin-bottom: 4px;
}}

.kpi-sub {{
  font-size: 13px;
  color: var(--text-secondary);
}}

.chart-row {{
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1.4fr);
  gap: var(--gap);
  margin-bottom: 24px;
}}

@media (max-width: 900px) {{
  .chart-row {{
    grid-template-columns: minmax(0, 1fr);
  }}
}}

.chart-card {{
  background: var(--bg-card);
  border-radius: var(--radius);
  padding: 18px 20px;
  box-shadow: var(--shadow-soft);
}}

.chart-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}}

.chart-title {{
  font-size: 16px;
  margin: 0;
}}

.chart-subtitle {{
  font-size: 12px;
  color: var(--text-secondary);
}}

.chart-container canvas {{
  width: 100%;
  height: 260px;
}}

.table-section {{
  background: var(--bg-card);
  border-radius: var(--radius);
  padding: 18px 20px;
  box-shadow: var(--shadow-soft);
  margin-bottom: 24px;
}}

.table-section h2 {{
  margin: 0 0 10px;
  font-size: 16px;
}}

.table-section p {{
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--text-secondary);
}}

.rfm-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}}

.rfm-table th,
.rfm-table td {{
  padding: 6px 8px;
  text-align: left;
}}

.rfm-table thead {{
  background: rgba(15,23,42,0.8);
}}

.rfm-table tbody tr:nth-child(even) {{
  background: rgba(15,23,42,0.5);
}}

.rfm-segment-Best {{ color: var(--positive); }}
.rfm-segment-At\\ risk {{ color: var(--negative); }}

.dashboard-footer {{
  font-size: 12px;
  color: var(--text-secondary);
  text-align: right;
  margin-top: 8px;
}}
</style>
</head>
<body>
<div class="dashboard-container">
  <header class="dashboard-header">
    <div>
      <h1>Retail BI Analyst &mdash; Web Report</h1>
      <span class="chart-subtitle">Sales performance overview</span>
    </div>
    <div class="dashboard-meta">
      <span>Generated at: {datetime.now().strftime("%Y-%m-%d %H:%M")}</span>
      <span>Data as of: {escape(latest_date_str, quote=True)}</span>
    </div>
  </header>

  <section class="kpi-row">
    <article class="kpi-card">
      <div class="kpi-label">Total Revenue</div>
      <div class="kpi-value">${kpi.total_revenue:,.2f}</div>
      <div class="kpi-sub">Sum of all transactions</div>
    </article>
    <article class="kpi-card">
      <div class="kpi-label">Average Bill</div>
      <div class="kpi-value">${kpi.avg_ticket:,.2f}</div>
      <div class="kpi-sub">Average value per transaction</div>
    </article>
    <article class="kpi-card">
      <div class="kpi-label">Transactions</div>
      <div class="kpi-value">{escape(str(kpi.transactions_count), quote=True)}</div>
      <div class="kpi-sub">Total number of sales</div>
    </article>
    <article class="kpi-card">
      <div class="kpi-label">Unique Customers</div>
      <div class="kpi-value">{escape(str(kpi.unique_customers), quote=True)}</div>
      <div class="kpi-sub">Distinct customers in the period</div>
    </article>
  </section>

  <section class="chart-row">
    <article class="chart-card">
      <div class="chart-header">
        <h2 class="chart-title">Revenue Over Time</h2>
        <span class="chart-subtitle">Daily revenue trend</span>
      </div>
      <div class="chart-container">
        <canvas id="revenueChart"></canvas>
      </div>
    </article>

    <article class="chart-card">
      <div class="chart-header">
        <h2 class="chart-title">Customers by Segment</h2>
        <span class="chart-subtitle">RFM segments distribution</span>
      </div>
      <div class="chart-container">
        <canvas id="segmentChart"></canvas>
      </div>
    </article>
  </section>

  <section class="table-section">
    <h2>RFM Analysis Details</h2>
    <p>Each row represents a customer with recency, frequency, monetary, and segment assignment.</p>
    <table class="rfm-table">
      <thead>
        <tr>
          <th>Customer</th>
          <th>Recency (days)</th>
          <th>Frequency</th>
          <th>Monetary</th>
          <th>Segment</th>
        </tr>
      </thead>
      <tbody>
"""

    # Dynamically build and format RFM customer table HTML rows
    for cid, scores in rfm.items():
        # replace spaces in segment names with underscores to construct safe CSS class name
        segment_class = {"Best": "rfm-segment-Best", "Loyal": "rfm-segment-Loyal", "Regular": "rfm-segment-Regular", "At risk": "rfm-segment-At_risk"}.get(scores.segment, "rfm-segment-Regular")
        # append HTML table row string
        html += (
            f"<tr>"
            f"<td>{escape(str(cid), quote=True)}</td>"
            f"<td>{escape(str(scores.recency_days), quote=True)}</td>"
            f"<td>{escape(str(scores.frequency), quote=True)}</td>"
            f"<td>${scores.monetary:,.2f}</td>"
            f"<td class=\"{segment_class}\">{escape(str(scores.segment), quote=True)}</td>"
            f"</tr>\n"
        )

    # append closing HTML elements and inline JS Chart.js initialization logic
    html += f"""      </tbody>
    </table>
  </section>

  <footer class="dashboard-footer">
    <span>Insights powered by Retail BI Analyst</span>
  </footer>
</div>

<script>
const revenueLabels = {json_revenue_labels};
const revenueData = {json_revenue_values};
const segmentLabels = {json_segment_labels};
const segmentData = {json_segment_values};

// Revenue chart (line)
const revenueCtx = document.getElementById('revenueChart');
if (revenueCtx && revenueLabels.length > 0) {{
  new Chart(revenueCtx, {{
    type: 'line',
    data: {{
      labels: revenueLabels,
      datasets: [{{
        label: 'Revenue',
        data: revenueData,
        borderColor: '#38bdf8',
        backgroundColor: 'rgba(56, 189, 248, 0.15)',
        tension: 0.25,
        fill: true,
        pointRadius: 3,
      }}],
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{
          display: true,
        }},
        tooltip: {{
          callbacks: {{
            label: function(ctx) {{
              const value = ctx.parsed.y || 0;
              return 'Revenue: $' + value.toLocaleString();
            }}
          }}
        }}
      }},
      scales: {{
        x: {{
          ticks: {{
            maxRotation: 60,
            minRotation: 30
          }}
        }},
        y: {{
          beginAtZero: true
        }}
      }}
    }},
  }});
}} else {{
  if (revenueCtx) {{
    revenueCtx.parentElement.innerHTML =
      '<p style="font-size:13px;color:#9ca3af;">No revenue time series available for this dataset.</p>';
  }}
}}

// Segment chart (bar)
const segmentCtx = document.getElementById('segmentChart');
if (segmentCtx && segmentLabels.length > 0) {{
  new Chart(segmentCtx, {{
    type: 'bar',
    data: {{
      labels: segmentLabels,
      datasets: [{{
        label: 'Customers',
        data: segmentData,
        backgroundColor: ['#22c55e', '#3b82f6', '#ef4444', '#e5e7eb'],
        borderRadius: 6,
      }}],
    }},
    options: {{
      indexAxis: 'y',
      responsive: true,
      plugins: {{
        legend: {{
          display: false
        }},
        tooltip: {{
          callbacks: {{
            label: function(ctx) {{
              const value = ctx.parsed.x || 0;
              return 'Customers: ' + value.toLocaleString();
            }}
          }}
        }}
      }},
      scales: {{
        x: {{
          beginAtZero: true
        }},
        y: {{
          ticks: {{
            color: '#e5e7eb'
          }}
        }}
      }}
    }},
  }});
}} else {{
  if (segmentCtx) {{
    segmentCtx.parentElement.innerHTML =
      '<p style="font-size:13px;color:#9ca3af;">No RFM segment data available for this dataset.</p>';
  }}
}}
</script>
</body>
</html>
"""

    # return fully assembled HTML document string
    return html