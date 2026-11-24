"""One fresh test-point-2-4 Dify experiment, or inspect an existing run."""
import argparse
import hashlib
import json
import time

import httpx

from multiflight.schemas import GroundCorrectionParameters
from multiflight.settings import RUN_DIR


def inspect(job):
    folder=RUN_DIR/job["id"];result=job.get("result") or {}
    records=json.loads((folder/"records.json").read_text(encoding="utf-8")) if (folder/"records.json").exists() else []
    decisions=json.loads((folder/"decisions.json").read_text(encoding="utf-8")) if (folder/"decisions.json").exists() else []
    steps=[r for r in records if r["kind"]=="step"]
    dify=result.get("dify",{});p=job["payload"]["parameters"]
    prompt=(folder/"compiled_prompt.md").read_text(encoding="utf-8")
    checks={"task_passed":job["status"]=="succeeded" and bool(result.get("evaluation",{}).get("passed")),
        "parameters_consistent":p==result.get("parameters")==result.get("evaluation",{}).get("parameters"),
        "fresh_call_each_step":bool(steps) and len(steps)==len(decisions)==dify.get("model_calls")
           and dify.get("reused_decisions")==0 and all(d["source"]=="live_dify" for d in decisions),
        "prompt_hash_matches":hashlib.sha256(prompt.encode()).hexdigest()==result.get("prompt",{}).get("prompt_hash")}
    report={"run_id":job["id"],"status":job["status"],"error":job.get("error"),"parameters":p,
            "checks":checks,"passed":all(checks.values()),"dify":dify,"evaluation":result.get("evaluation"),
            "final_state":steps[-1]["result"]["state"] if steps else None}
    (folder/"correction_verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--run-id")
    parser.add_argument("--prompt-version",choices=["0.4.0","0.4.1"],default="0.4.0")
    args=parser.parse_args()
    with httpx.Client(base_url="http://127.0.0.1:8000",timeout=20,trust_env=False,
                      limits=httpx.Limits(max_keepalive_connections=0)) as c:
        rid=args.run_id
        if not rid:
            response=c.post("/api/runs",json={"scene_id":"ground_direction","prompt_version":args.prompt_version,
                "parameters":GroundCorrectionParameters().model_dump()})
            response.raise_for_status();rid=response.json()["id"]
        print("RUN_ID="+rid,flush=True);last=None
        for _ in range(360):
            try:
                response=c.get("/api/runs/"+rid);response.raise_for_status();job=response.json()
            except httpx.TransportError:
                print("Polling interrupted; retrying read-only for "+rid,flush=True)
                time.sleep(5);continue
            if job["message"]!=last:print(job["status"],job["message"],flush=True);last=job["message"]
            if job["status"] in {"succeeded","completed_with_failures","failed"}:
                report=inspect(job);print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
                raise SystemExit(0 if report["passed"] else 1)
            time.sleep(5)
    raise TimeoutError("Still active; inspect "+rid+" before submitting another experiment")
