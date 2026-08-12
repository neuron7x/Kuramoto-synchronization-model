# mypy: ignore-errors
# ruff: noqa
# fmt: off
# SPDX-License-Identifier: MIT
"""Fail-closed validator for the GeoSync Epistemic Rhombus manifest."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
from typing import Any, Iterator
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
DEFAULT_MANIFEST=Path("governance/epistemic_rhombus_manifest.jsonl")
DEFAULT_SCHEMA=Path("schemas/governance/epistemic_rhombus_manifest.schema.json")
WORKFLOW_ROOT=Path(".github/workflows")
WORKFLOW_SUFFIXES={".yml",".yaml"}
FORBIDDEN_PR_TARGET_TRIGGER="pull_request"+"_target"
class ManifestReadError(ValueError): pass
def iter_jsonl(path:Path)->Iterator[tuple[int,dict[str,Any]]]:
    with path.open("r",encoding="utf-8") as s:
        for n,line in enumerate(s,1):
            if not line.strip(): continue
            try: v=json.loads(line)
            except json.JSONDecodeError as e: raise ManifestReadError(f"line {n}: invalid JSON: {e.msg}") from e
            if not isinstance(v,dict): raise ManifestReadError(f"line {n}: record must be a JSON object")
            yield n,v
def load_schema(path:Path)->dict[str,Any]:
    try: schema=json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e: raise ValueError(f"schema {path}: invalid JSON: {e.msg}") from e
    if not isinstance(schema,dict): raise ValueError(f"schema {path}: root must be a JSON object")
    Draft202012Validator.check_schema(schema); return schema
def required_axis_order(schema:dict[str,Any])->list[str]:
    enum=schema.get("properties",{}).get("axis",{}).get("enum")
    if not isinstance(enum,list) or not all(isinstance(x,str) for x in enum): raise ValueError("schema must define properties.axis.enum as a string array")
    return list(enum)
def required_axes(schema:dict[str,Any])->set[str]: return set(required_axis_order(schema))
def format_schema_error(error:ValidationError)->str:
    loc=".".join(str(p) for p in error.absolute_path)
    return f"{loc}: {error.message}" if loc else error.message
def command_target_exists(command:list[str],root:Path)->bool:
    if not command: return False
    t=command[0]
    if not isinstance(t,str): return False
    if t.startswith("/"): return Path(t).exists()
    if t.startswith("./") or "/" in t: return (root/t).exists()
    return True
def _is_workflow_target(t:str)->bool:
    p=Path(t); return (not p.is_absolute() and len(p.parts)>=3 and Path(*p.parts[:2])==WORKFLOW_ROOT and p.suffix in WORKFLOW_SUFFIXES)
def _workflow_declares_trigger(text:str,trig:str)->bool: return re.search(rf"(?m)^\s{{0,4}}{re.escape(trig)}\s*:",text) is not None
def _workflow_declares_readonly_contents(text:str)->bool:
    return re.search(r"(?m)^permissions\s*:\s*$",text) is not None and re.search(r"(?m)^\s{2}contents\s*:\s*read\s*$",text) is not None
def validate_external_gate(command:list[str],repo_root:Path,prefix:str)->list[str]:
    t=command[0]; errs=[]
    if not _is_workflow_target(t): return [f"{prefix}: external_gate command must target .github/workflows/*.yml or *.yaml, got: {t}"]
    wf=repo_root/t
    if not wf.exists(): return [f"{prefix}: enforcement command target does not exist: {t}"]
    text=wf.read_text(encoding="utf-8")
    if _workflow_declares_trigger(text,FORBIDDEN_PR_TARGET_TRIGGER): errs.append(f"{prefix}: external gate must not use {FORBIDDEN_PR_TARGET_TRIGGER}: {t}")
    if not (_workflow_declares_trigger(text,"pull_request") or _workflow_declares_trigger(text,"merge_group")): errs.append(f"{prefix}: external gate workflow must declare pull_request or merge_group trigger: {t}")
    if not _workflow_declares_readonly_contents(text): errs.append(f"{prefix}: external gate workflow must declare permissions.contents=read: {t}")
    return errs
def _record_prefix(n:int,r:dict[str,Any])->str:
    rid=r.get("record_id"); return f"line {n} ({rid if isinstance(rid,str) else f'line {n}'})"
def _enforcement_target(r:dict[str,Any])->str|None:
    e=r.get("enforcement"); c=e.get("command") if isinstance(e,dict) else None
    return c[0] if isinstance(c,list) and c and isinstance(c[0],str) else None
def _sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as s:
        for b in iter(lambda:s.read(1048576),b""): h.update(b)
    return h.hexdigest()
def validate_manifest(manifest_path:Path,schema_path:Path,repo_root:Path)->list[str]:
    schema=load_schema(schema_path); val=Draft202012Validator(schema); order=required_axis_order(schema)
    axis_id={a:f"ER-{i}" for i,a in enumerate(order,1)}; axes={}; gids={}; rids={}; errs=[]; count=0
    for n,r in iter_jsonl(manifest_path):
        count+=1; p=_record_prefix(n,r)
        for e in sorted(val.iter_errors(r),key=lambda x:list(x.absolute_path)): errs.append(f"{p}: {format_schema_error(e)}")
        rid=r.get("record_id")
        if isinstance(rid,str):
            if rid in rids: errs.append(f"{p}: duplicate record_id {rid!r} (first seen on line {rids[rid]})")
            else: rids[rid]=n
        axis=r.get("axis")
        if isinstance(axis,str):
            if isinstance(rid,str) and rid!=axis_id.get(axis): errs.append(f"{p}: axis {axis!r} must use record_id {axis_id.get(axis)!r}, got {rid!r}")
            if axis in axes: errs.append(f"{p}: duplicate axis {axis!r} (first seen on line {axes[axis]})")
            else: axes[axis]=n
        for g in r.get("control_gates",[]) if isinstance(r.get("control_gates"),list) else []:
            if not isinstance(g,str): continue
            if g in gids: errs.append(f"{p}: duplicate control gate {g!r} (first seen on line {gids[g]})")
            else: gids[g]=n
        e=r.get("enforcement")
        if isinstance(e,dict):
            c=e.get("command"); mode=e.get("mode")
            if isinstance(c,list) and all(isinstance(x,str) for x in c):
                if mode=="external_gate": errs.extend(validate_external_gate(c,repo_root,p))
                elif not command_target_exists(c,repo_root): errs.append(f"{p}: enforcement command target does not exist: {c[0]}")
    if count==0: errs.append("manifest: no records found")
    missing=sorted(set(order)-set(axes))
    if missing: errs.append(f"manifest: missing axes: {', '.join(missing)}")
    return errs
def build_report(manifest_path:Path,schema_path:Path,repo_root:Path,errors:list[str])->dict[str,Any]:
    rec=[{"axis":r.get("axis"),"control_gates":r.get("control_gates"),"enforcement_target":_enforcement_target(r),"line":n,"record_id":r.get("record_id")} for n,r in iter_jsonl(manifest_path)]
    return {"schema_version":1,"status":"PASS" if not errors else "FAIL","manifest_path":str(manifest_path),"manifest_sha256":_sha256(manifest_path),"schema_path":str(schema_path),"schema_sha256":_sha256(schema_path),"repo_root":str(repo_root),"record_count":len(rec),"axes":[r["axis"] for r in rec],"records":rec,"errors":errors}
def write_report(path:Path,report:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
def main(argv:list[str]|None=None)->int:
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument("manifest",nargs="?",default=DEFAULT_MANIFEST,type=Path); ap.add_argument("--schema",default=DEFAULT_SCHEMA,type=Path); ap.add_argument("--repo-root",default=Path.cwd(),type=Path); ap.add_argument("--report",type=Path); a=ap.parse_args(argv)
    try:
        errs=validate_manifest(a.manifest,a.schema,a.repo_root)
        if a.report is not None: write_report(a.report,build_report(a.manifest,a.schema,a.repo_root,errs))
    except (OSError,ValueError) as e: print(f"manifest validation failed: {e}",file=sys.stderr); return 2
    if errs:
        print("manifest validation failed:",file=sys.stderr)
        for e in errs: print(f"- {e}",file=sys.stderr)
        return 1
    print(f"validated Epistemic Rhombus manifest: {a.manifest}"); return 0
if __name__=="__main__": raise SystemExit(main())
