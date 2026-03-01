"""SQLite-backed cache for financial time series data."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_CREATE_TIME_SERIES = """
CREATE TABLE IF NOT EXISTS time_series (
    instrument_id TEXT NOT NULL,
    date          TEXT NOT NULL,
    value         REAL,
    open          REAL,
    high          REAL,
    low           REAL,
    close         REAL,
    volume        REAL,
    metadata      TEXT,
    PRIMARY KEY (instrument_id, date)
)
"""

_CREATE_CACHE_METADATA = """
CREATE TABLE IF NOT EXISTS cache_metadata (
    instrument_id TEXT PRIMARY KEY,
    last_updated  TEXT,
    source        TEXT,
    earliest_date TEXT,
    latest_date   TEXT
)
"""


class DataCache:
    """Local SQLite cache for financial time series data.

    Thread-safe — the underlying connection uses *check_same_thread=False*
    so it can be shared across threads (SQLite itself serialises writes).
    """

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TIME_SERIES)
        self._conn.execute(_CREATE_CACHE_METADATA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store_series(
        self,
        instrument_id: str,
        df: "pd.DataFrame",
        source: str,
    ) -> None:
        """Persist a pandas DataFrame of time series rows.

        The DataFrame index (or a ``date`` column) supplies the date.
        Recognised value columns: ``value``, ``open``, ``high``, ``low``,
        ``close``, ``volume``.  Any extra columns are JSON-serialised into
        the ``metadata`` field.
        """
        import pandas as pd

        if df.empty:
            return

        records = self._dataframe_to_records(df, instrument_id)

        self._conn.executemany(
            """
            INSERT OR REPLACE INTO time_series
                (instrument_id, date, value, open, high, low, close, volume, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )

        dates = [r[1] for r in records]
        earliest = min(dates)
        latest = max(dates)
        now_iso = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            """
            INSERT INTO cache_metadata
                (instrument_id, last_updated, source, earliest_date, latest_date)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(instrument_id) DO UPDATE SET
                last_updated  = excluded.last_updated,
                source        = excluded.source,
                earliest_date = MIN(cache_metadata.earliest_date, excluded.earliest_date),
                latest_date   = MAX(cache_metadata.latest_date, excluded.latest_date)
            """,
            (instrument_id, now_iso, source, earliest, latest),
        )
        self._conn.commit()

    def get_series(
        self,
        instrument_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> "pd.DataFrame":
        """Return cached rows as a pandas DataFrame indexed by date."""
        import pandas as pd

        clauses = ["instrument_id = ?"]
        params: list[str] = [instrument_id]

        if start_date is not None:
            clauses.append("date >= ?")
            params.append(start_date)
        if end_date is not None:
            clauses.append("date <= ?")
            params.append(end_date)

        where = " AND ".join(clauses)
        rows = self._conn.execute(
            f"SELECT * FROM time_series WHERE {where} ORDER BY date",
            params,
        ).fetchall()

        if not rows:
            return pd.DataFrame()

        return self._rows_to_dataframe(rows)

    def get_latest(self, instrument_id: str) -> dict | None:
        """Return the most recent cached data point, or *None*."""
        row = self._conn.execute(
            """
            SELECT * FROM time_series
            WHERE instrument_id = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (instrument_id,),
        ).fetchone()

        if row is None:
            return None

        result = dict(row)
        if result.get("metadata"):
            result["metadata"] = json.loads(result["metadata"])
        return result

    def is_fresh(self, instrument_id: str, max_age_hours: int = 24) -> bool:
        """Return *True* if cached data was updated within *max_age_hours*."""
        row = self._conn.execute(
            "SELECT last_updated FROM cache_metadata WHERE instrument_id = ?",
            (instrument_id,),
        ).fetchone()

        if row is None or row["last_updated"] is None:
            return False

        last_updated = datetime.fromisoformat(row["last_updated"])
        age = datetime.now(timezone.utc) - last_updated
        return age.total_seconds() < max_age_hours * 3600

    def get_date_range(self, instrument_id: str) -> tuple[str, str] | None:
        """Return ``(earliest_date, latest_date)`` or *None*."""
        row = self._conn.execute(
            "SELECT earliest_date, latest_date FROM cache_metadata WHERE instrument_id = ?",
            (instrument_id,),
        ).fetchone()

        if row is None:
            return None
        return (row["earliest_date"], row["latest_date"])

    def clear(self, instrument_id: str | None = None) -> None:
        """Delete cached data.  If *instrument_id* is ``None``, clear everything."""
        if instrument_id is None:
            self._conn.execute("DELETE FROM time_series")
            self._conn.execute("DELETE FROM cache_metadata")
        else:
            self._conn.execute(
                "DELETE FROM time_series WHERE instrument_id = ?",
                (instrument_id,),
            )
            self._conn.execute(
                "DELETE FROM cache_metadata WHERE instrument_id = ?",
                (instrument_id,),
            )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _dataframe_to_records(
        df: "pd.DataFrame",
        instrument_id: str,
    ) -> list[tuple]:
        """Convert a DataFrame into a list of insert-ready tuples.

        Handles DataFrames that have:
        * A ``date`` column **or** a DatetimeIndex / string index.
        * Full OHLCV columns, a single ``value`` / ``close`` column, or a mix.
        """
        import pandas as pd

        known_cols = {"date", "value", "open", "high", "low", "close", "volume"}
        df = df.copy()

        # Normalise the date from the index if there's no explicit column.
        if "date" not in df.columns:
            df = df.reset_index()
            # The reset index may produce 'index', 'Date', 'DATE', etc.
            for candidate in ("index", "Index", "Date", "DATE", "Datetime", "datetime"):
                if candidate in df.columns:
                    df.rename(columns={candidate: "date"}, inplace=True)
                    break

        if "date" not in df.columns:
            raise ValueError(
                "DataFrame must have a 'date' column or a DatetimeIndex"
            )

        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

        # Identify extra columns to pack into metadata JSON.
        extra_cols = [c for c in df.columns if c.lower() not in known_cols]

        records: list[tuple] = []
        for _, row in df.iterrows():
            meta = (
                json.dumps({c: _safe_value(row[c]) for c in extra_cols})
                if extra_cols
                else None
            )
            records.append((
                instrument_id,
                row["date"],
                _get(row, "value"),
                _get(row, "open"),
                _get(row, "high"),
                _get(row, "low"),
                _get(row, "close"),
                _get(row, "volume"),
                meta,
            ))
        return records

    @staticmethod
    def _rows_to_dataframe(rows: list[sqlite3.Row]) -> "pd.DataFrame":
        import pandas as pd

        df = pd.DataFrame([dict(r) for r in rows])
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df.drop(columns=["instrument_id"], inplace=True)

        # Unpack metadata JSON back into columns.
        if "metadata" in df.columns:
            meta_series = df["metadata"].apply(
                lambda v: json.loads(v) if v else {}
            )
            meta_df = pd.DataFrame(meta_series.tolist(), index=df.index)
            if not meta_df.empty and meta_df.columns.size:
                df = pd.concat([df.drop(columns=["metadata"]), meta_df], axis=1)
            else:
                df.drop(columns=["metadata"], inplace=True)

        return df


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _get(row: "pd.Series", col: str) -> float | None:
    """Return column value as float, or *None* if absent / NaN."""
    import math

    if col not in row.index:
        return None
    val = row[col]
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _safe_value(val: object) -> object:
    """Make a value JSON-serialisable."""
    import math

    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    try:
        json.dumps(val)
        return val
    except (TypeError, ValueError):
        return str(val)
