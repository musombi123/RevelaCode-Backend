# backend/jumuiya/elimu/sync/importer.py
from __future__ import annotations
import csv,io,json

def parse_csv(text):
    reader=csv.DictReader(io.StringIO(text)); return [dict(row) for row in reader]

def parse_json(text):
    data=json.loads(text)
    if not isinstance(data,list):raise ValueError("JSON import must contain an array of records.")
    return [x for x in data if isinstance(x,dict)]

def parse_xlsx(data):
    try:
        from openpyxl import load_workbook
    except ImportError as exc:raise RuntimeError("openpyxl is required for XLSX imports.") from exc
    wb=load_workbook(io.BytesIO(data),read_only=True,data_only=True); ws=wb.active
    rows=list(ws.iter_rows(values_only=True))
    if not rows:return []
    headers=[str(x).strip() if x is not None else "" for x in rows[0]]
    return [dict(zip(headers,row)) for row in rows[1:]]

def preview(records):
    return {"rows":len(records),"columns":sorted({k for r in records for k in r}),"sample":records[:5]}
