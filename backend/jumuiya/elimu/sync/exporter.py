# backend/jumuiya/elimu/sync/exporter.py
from __future__ import annotations
import csv,io,json

def json_export(records):return json.dumps(records,default=str,ensure_ascii=False,indent=2)
def csv_export(records):
    rows=list(records); fields=sorted({k for r in rows for k in r}); out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=fields); writer.writeheader();
    for r in rows:writer.writerow({k:r.get(k) for k in fields})
    return out.getvalue()
