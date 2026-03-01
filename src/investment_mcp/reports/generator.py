"""Plotly chart builder and HTML report generator.

Builds interactive Plotly charts (line, candlestick, yield-curve, comparison)
and assembles HTML reports via Jinja2 templates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from jinja2 import Environment, FileSystemLoader

# ---------------------------------------------------------------------------
# Dark-theme constants shared across every chart
# ---------------------------------------------------------------------------
PAPER_BG = "#0a0e17"
PLOT_BG = "#111827"
FONT_COLOR = "#f1f5f9"
GRID_COLOR = "#1e293b"
DEFAULT_COLOR = "#3b82f6"

PALETTE = [
    "#00b4d8",
    "#ff6b6b",
    "#ffd166",
    "#06d6a0",
    "#118ab2",
    "#ef476f",
    "#8338ec",
    "#fb5607",
    "#3a86ff",
    "#ffbe0b",
]

DATE_RANGE_BUTTONS = [
    dict(count=1, label="1M", step="month", stepmode="backward"),
    dict(count=3, label="3M", step="month", stepmode="backward"),
    dict(count=6, label="6M", step="month", stepmode="backward"),
    dict(count=1, label="1Y", step="year", stepmode="backward"),
    dict(count=5, label="5Y", step="year", stepmode="backward"),
    dict(step="all", label="ALL"),
]


def _dark_layout(**overrides: Any) -> dict[str, Any]:
    """Return a base dark-theme layout dict, merged with *overrides*."""
    base: dict[str, Any] = dict(
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(color=FONT_COLOR, family="Inter, system-ui, sans-serif"),
        margin=dict(l=60, r=30, t=50, b=40),
        hovermode="x unified",
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=FONT_COLOR)),
        xaxis=dict(
            gridcolor=GRID_COLOR,
            rangeslider=dict(visible=True),
            rangeselector=dict(buttons=DATE_RANGE_BUTTONS),
        ),
        yaxis=dict(gridcolor=GRID_COLOR),
    )
    base.update(overrides)
    return base


def _to_json(fig: go.Figure) -> str:
    """Serialize a Plotly figure to a JSON string."""
    return pio.to_json(fig, validate=False)


# ===================================================================
# ChartBuilder
# ===================================================================


class ChartBuilder:
    """Builds Plotly chart JSON strings for investment data visualisation."""

    # ---- single time-series line chart --------------------------------

    @staticmethod
    def build_line_chart(
        df: pd.DataFrame,
        title: str,
        y_label: str,
        color: str = DEFAULT_COLOR,
    ) -> str:
        """Return Plotly JSON for a single time-series line chart.

        Parameters
        ----------
        df:
            DataFrame with a ``DatetimeIndex`` and a single value column.
        title:
            Chart title.
        y_label:
            Y-axis label.
        color:
            Line colour (CSS hex string).

        Returns
        -------
        str
            Plotly JSON string ready for embedding.
        """
        col = df.columns[0]
        use_gl = len(df) > 2000

        trace_cls = go.Scattergl if use_gl else go.Scatter
        trace = trace_cls(
            x=df.index,
            y=df[col],
            mode="lines",
            name=col,
            line=dict(color=color, width=2),
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.2f}<extra></extra>",
        )
        layout = _dark_layout(title=dict(text=title, x=0.5), yaxis_title=y_label)
        fig = go.Figure(data=[trace], layout=layout)
        return _to_json(fig)

    # ---- multi-line overlay -------------------------------------------

    @staticmethod
    def build_multi_line_chart(
        series: dict[str, pd.DataFrame],
        title: str,
        y_label: str,
    ) -> str:
        """Return Plotly JSON for multiple overlaid time-series.

        Parameters
        ----------
        series:
            Mapping of *label* → DataFrame (``DatetimeIndex``, single column).
        title:
            Chart title.
        y_label:
            Y-axis label.
        """
        traces: list[go.Scatter | go.Scattergl] = []
        for idx, (name, df) in enumerate(series.items()):
            col = df.columns[0]
            color = PALETTE[idx % len(PALETTE)]
            use_gl = len(df) > 2000
            trace_cls = go.Scattergl if use_gl else go.Scatter
            traces.append(
                trace_cls(
                    x=df.index,
                    y=df[col],
                    mode="lines",
                    name=name,
                    line=dict(color=color, width=2),
                    hovertemplate=f"{name}: " + "%{y:,.2f}<extra></extra>",
                )
            )

        layout = _dark_layout(
            title=dict(text=title, x=0.5),
            yaxis_title=y_label,
            showlegend=True,
        )
        fig = go.Figure(data=traces, layout=layout)
        return _to_json(fig)

    # ---- OHLCV candlestick -------------------------------------------

    @staticmethod
    def build_candlestick_chart(df: pd.DataFrame, title: str) -> str:
        """Return Plotly JSON for an OHLCV candlestick chart.

        Parameters
        ----------
        df:
            DataFrame with ``DatetimeIndex`` and columns
            ``open``, ``high``, ``low``, ``close`` (case-insensitive).
        title:
            Chart title.

        Raises
        ------
        ValueError
            If required OHLC columns are missing.
        """
        cols = {c.lower(): c for c in df.columns}
        required = {"open", "high", "low", "close"}
        missing = required - cols.keys()
        if missing:
            raise ValueError(f"Missing OHLC columns: {missing}")

        candle = go.Candlestick(
            x=df.index,
            open=df[cols["open"]],
            high=df[cols["high"]],
            low=df[cols["low"]],
            close=df[cols["close"]],
            increasing_line_color="#06d6a0",
            decreasing_line_color="#ef476f",
            name="OHLC",
        )

        layout = _dark_layout(
            title=dict(text=title, x=0.5),
            yaxis_title="Price",
        )
        fig = go.Figure(data=[candle], layout=layout)
        return _to_json(fig)

    # ---- normalised comparison (rebased to 100) -----------------------

    @staticmethod
    def build_comparison_chart(
        series: dict[str, pd.DataFrame],
        title: str,
        normalize: bool = True,
    ) -> str:
        """Return Plotly JSON comparing multiple instruments.

        Parameters
        ----------
        series:
            Mapping of *label* → DataFrame (``DatetimeIndex``, single column).
        title:
            Chart title.
        normalize:
            If ``True`` each series is rebased so its first value equals 100.
        """
        traces: list[go.Scatter | go.Scattergl] = []
        for idx, (name, df) in enumerate(series.items()):
            col = df.columns[0]
            values = df[col].dropna()
            if normalize and len(values) > 0:
                values = values / values.iloc[0] * 100.0
            color = PALETTE[idx % len(PALETTE)]
            use_gl = len(values) > 2000
            trace_cls = go.Scattergl if use_gl else go.Scatter
            traces.append(
                trace_cls(
                    x=values.index,
                    y=values,
                    mode="lines",
                    name=name,
                    line=dict(color=color, width=2),
                    hovertemplate=f"{name}: " + "%{y:,.2f}<extra></extra>",
                )
            )

        y_label = "Rebased (100)" if normalize else "Value"
        layout = _dark_layout(
            title=dict(text=title, x=0.5),
            yaxis_title=y_label,
            showlegend=True,
        )
        fig = go.Figure(data=traces, layout=layout)
        return _to_json(fig)

    # ---- yield-curve snapshot ----------------------------------------

    @staticmethod
    def build_yield_curve_snapshot(
        yields: dict[str, float],
        date: str,
    ) -> str:
        """Return Plotly JSON for a single-date yield-curve snapshot.

        Parameters
        ----------
        yields:
            Mapping of maturity label (e.g. ``"2Y"``) to yield value.
        date:
            Date string shown in the chart title (e.g. ``"2024-06-01"``).
        """
        maturities = list(yields.keys())
        values = list(yields.values())

        trace = go.Scatter(
            x=maturities,
            y=values,
            mode="lines+markers",
            line=dict(color=DEFAULT_COLOR, width=3),
            marker=dict(size=8, color=DEFAULT_COLOR),
            hovertemplate="%{x}: %{y:.3f}%<extra></extra>",
        )

        layout = _dark_layout(
            title=dict(text=f"Yield Curve — {date}", x=0.5),
            xaxis=dict(
                gridcolor=GRID_COLOR,
                title="Maturity",
                rangeslider=dict(visible=False),
            ),
            yaxis=dict(gridcolor=GRID_COLOR, title="Yield (%)"),
            hovermode="x",
        )
        fig = go.Figure(data=[trace], layout=layout)
        return _to_json(fig)


# ===================================================================
# ReportGenerator
# ===================================================================


class ReportGenerator:
    """Renders Jinja2 HTML reports containing Plotly charts.

    Parameters
    ----------
    template_dir:
        Path to the directory containing ``*.html`` Jinja2 templates.
    """

    def __init__(self, template_dir: Path) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True,
        )

    # ---- dashboard ----------------------------------------------------

    def generate_dashboard(
        self,
        charts: list[dict[str, Any]],
        summary_cards: list[dict[str, Any]],
        output_path: Path,
    ) -> Path:
        """Render *dashboard.html* with embedded Plotly charts.

        Parameters
        ----------
        charts:
            List of dicts, each with ``"id"``, ``"title"``, ``"json"`` keys
            (the ``json`` value is a Plotly JSON string).
        summary_cards:
            List of dicts with ``"label"``, ``"value"``, and optional ``"change"``
            keys rendered as KPI cards.
        output_path:
            Destination file path (parent directories are created if needed).

        Returns
        -------
        Path
            The resolved *output_path*.
        """
        template = self._env.get_template("dashboard.html")
        from datetime import datetime
        html = template.render(
            charts=charts,
            summary_cards=summary_cards,
            last_updated=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path

    # ---- instrument detail page ---------------------------------------

    def generate_detail(
        self,
        instrument: dict[str, Any],
        chart_json: str,
        stats: dict[str, Any],
        recent_data: list[dict[str, Any]],
        output_path: Path,
    ) -> Path:
        """Render *detail.html* for a single instrument.

        Parameters
        ----------
        instrument:
            Dict with at least ``"name"`` and ``"symbol"`` keys.
        chart_json:
            Plotly JSON string for the primary chart.
        stats:
            Summary statistics dict (e.g. ``{"52W High": 150.0, ...}``).
        recent_data:
            List of row dicts for the recent-data table.
        output_path:
            Destination file path.

        Returns
        -------
        Path
            The resolved *output_path*.
        """
        template = self._env.get_template("detail.html")
        from datetime import datetime
        html = template.render(
            instrument=instrument,
            chart_json=chart_json,
            stats=stats,
            recent_data=recent_data,
            last_updated=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path

    # ---- index page ---------------------------------------------------

    def generate_index(
        self,
        reports: list[dict[str, Any]],
        output_path: Path,
    ) -> Path:
        """Render *index.html* linking to all available reports.

        Parameters
        ----------
        reports:
            List of dicts with ``"title"``, ``"url"`` (relative path), and
            optional ``"description"`` keys.
        output_path:
            Destination file path (e.g. ``docs/index.html``).

        Returns
        -------
        Path
            The resolved *output_path*.
        """
        template = self._env.get_template("index.html")
        html = template.render(reports=reports)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path
