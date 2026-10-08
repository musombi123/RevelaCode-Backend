# backend/jumuiya/elimu/sync/conflict.py
from __future__ import annotations
from copy import deepcopy

def _stamp(r): return r.get("updated_at") or r.get("version") or 0

def compare(local,cloud,base=None):
    local=local or {}; cloud=cloud or {}; base=base or {}
    if not local:return {"status":"new_cloud","record":deepcopy(cloud)}
    if not cloud:return {"status":"new_local","record":deepcopy(local)}
    if base:
        local_changed={k for k,v in local.items() if v!=base.get(k)}
        cloud_changed={k for k,v in cloud.items() if v!=base.get(k)}
        overlap=local_changed & cloud_changed
        if overlap:return {"status":"conflict","fields":sorted(overlap),"local_changed":sorted(local_changed),"cloud_changed":sorted(cloud_changed)}
        merged=deepcopy(base); merged.update({k:local[k] for k in local_changed}); merged.update({k:cloud[k] for k in cloud_changed}); return {"status":"merged","record":merged}
    if local==cloud:return {"status":"identical","record":deepcopy(cloud)}
    if _stamp(local)>_stamp(cloud):return {"status":"local_newer","record":deepcopy(local)}
    if _stamp(cloud)>_stamp(local):return {"status":"cloud_newer","record":deepcopy(cloud)}
    return {"status":"conflict","fields":sorted(set(local)|set(cloud))}

def resolve(decision,local,cloud,merged=None):
    if decision=="keep_local":return deepcopy(local)
    if decision=="keep_cloud":return deepcopy(cloud)
    if decision=="merge":
        if not isinstance(merged,dict):raise ValueError("merged record is required.")
        return deepcopy(merged)
    return None
