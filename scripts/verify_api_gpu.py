"""Run two real uploads against the complete HTTP/worker/persistence stack."""
import json
import sys
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from newsrec.api.app import create_app

report = []
scan = Path(sys.argv[1] if len(sys.argv) > 1 else "data/page.png")
if not scan.exists():
    sys.exit(f"{scan} missing -- pass a scan: uv run --extra gpu scripts/verify_api_gpu.py <image>")
start = perf_counter()
with TestClient(create_app(".runtime/verification")) as client:
    construct = perf_counter() - start
    for run in range(2):
        start = perf_counter()
        # Run 2 re-uploads the same bytes, so it also exercises the content-hash cache.
        response = client.post("/api/documents", files={"file": (scan.name, scan.read_bytes())})
        response.raise_for_status()
        page_id = response.json()["page_id"]
        upload_s = perf_counter() - start
        response = client.post(f"/api/pages/{page_id}/recognize", json={"engine": "structure"})
        response.raise_for_status()
        job_id = response.json()["job_id"]
        stream = client.get(f"/api/jobs/{job_id}/events")
        stream.raise_for_status()
        job = client.get(f"/api/jobs/{job_id}").json()
        assert job["status"] == "done", job
        timings = {e["stage"]: e.get("elapsed_ms") for e in job["events"]}
        page = client.get(f"/api/pages/{page_id}").json()
        result = {"run": run + 1, "construct_s": round(construct, 2), "upload_s": round(upload_s, 2),
                  "stages_ms": timings, "blocks": len(page["blocks"]),
                  "lines": sum(len(b["lines"]) for b in page["blocks"])}
        report.append(result)
        print(json.dumps(result), flush=True)
Path("bench/api-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
