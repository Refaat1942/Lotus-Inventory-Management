"""Excel reading and streaming writing shared by the web app and engine processes."""
from __future__ import annotations

import datetime
from pathlib import Path

import numpy as np
import pandas as pd


def floatify_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Convert Excel nullable Int64 qty columns to float64 (skip booleans)."""
    for col in df.columns:
        if pd.api.types.is_bool_dtype(df[col]):
            continue
        if pd.api.types.is_integer_dtype(df[col]):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
    return df


def read_excel_fast(source) -> pd.DataFrame:
    """Read an Excel file with calamine (~6x faster than openpyxl on large sheets),
    falling back to openpyxl if calamine is not installed or cannot read the file."""
    try:
        return pd.read_excel(source, engine="calamine")
    except Exception:
        if hasattr(source, "seek"):
            source.seek(0)
        return pd.read_excel(source, engine="openpyxl")


def read_excel_path(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    try:
        df = read_excel_fast(path)
    except Exception as exc:
        raise ValueError(f"Could not read Excel file '{path.name}': {exc}") from exc
    return floatify_numeric_columns(df)


_XLSX_HEADER_FORMAT = {"bold": True, "top": 1, "right": 1, "bottom": 1, "left": 1, "align": "center", "valign": "top"}


def _excel_cells(series: pd.Series) -> list:
    """Column values as pandas.to_excel would write them; None means an empty cell."""
    if pd.api.types.is_bool_dtype(series) or pd.api.types.is_integer_dtype(series):
        if not series.isna().any():
            return series.tolist()
    if pd.api.types.is_float_dtype(series) and not isinstance(series.dtype, pd.api.extensions.ExtensionDtype):
        arr = series.to_numpy(dtype=float)
        out = arr.astype(object)
        out[np.isnan(arr)] = None
        out[np.isposinf(arr)] = "inf"
        out[np.isneginf(arr)] = "-inf"
        return out.tolist()
    if pd.api.types.is_datetime64_any_dtype(series):
        return [None if pd.isna(v) else v.to_pydatetime() for v in series]

    def conv(v):
        if v is None or (pd.api.types.is_scalar(v) and pd.isna(v)):
            return None
        if isinstance(v, (bool, np.bool_)):
            return bool(v)
        if isinstance(v, (int, np.integer)):
            return int(v)
        if isinstance(v, (float, np.floating)):
            if np.isposinf(v):
                return "inf"
            if np.isneginf(v):
                return "-inf"
            return float(v)
        if isinstance(v, pd.Timestamp):
            return v.to_pydatetime()
        if isinstance(v, (datetime.datetime, datetime.date)):
            return v
        if isinstance(v, datetime.timedelta):
            return ("__timedelta__", v.total_seconds() / 86400)
        return str(v)[:32767]

    return [conv(v) for v in series.tolist()]


def stream_sheet(workbook, sheet_name: str, frame: pd.DataFrame, formats: dict) -> None:
    """Write a frame row by row (needed for xlsxwriter constant_memory mode).

    Same cell values/formats as DataFrame.to_excel(index=False), without holding
    every cell of the workbook in memory, which needed GBs for large sheets.
    """
    ws = workbook.add_worksheet(sheet_name)
    for c, name in enumerate(frame.columns):
        ws.write(0, c, name if isinstance(name, (str, int, float)) else str(name), formats["header"])
    columns = [_excel_cells(frame[col]) for col in frame.columns] if len(frame.columns) else []
    date_t, datetime_t = datetime.date, datetime.datetime
    for r, row in enumerate(zip(*columns), start=1):
        for c, v in enumerate(row):
            if v is None:
                continue
            if isinstance(v, datetime_t):
                ws.write_datetime(r, c, v, formats["datetime"])
            elif isinstance(v, date_t):
                ws.write_datetime(r, c, v, formats["date"])
            elif isinstance(v, tuple):
                ws.write_number(r, c, v[1], formats["timedelta"])
            else:
                ws.write(r, c, v)


def streaming_workbook(buffer):
    """xlsxwriter workbook in constant_memory mode (rows are streamed to temp
    files instead of keeping every cell in RAM) plus the formats stream_sheet uses."""
    import xlsxwriter

    workbook = xlsxwriter.Workbook(buffer, {"constant_memory": True})
    formats = {
        "header": workbook.add_format(_XLSX_HEADER_FORMAT),
        "datetime": workbook.add_format({"num_format": "YYYY-MM-DD HH:MM:SS"}),
        "date": workbook.add_format({"num_format": "YYYY-MM-DD"}),
        "timedelta": workbook.add_format({"num_format": "0"}),
    }
    return workbook, formats
