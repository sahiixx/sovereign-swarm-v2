"""sovereign_swarm/pipeline/worker.py — Async Queue Worker

Redis-ready: swap asyncio.Queue for redis.Redis() later.
Workers pick up PipelineLeads and run Extract → Validate → Enrich → Route.
"""
from __future__ import annotations

import asyncio, json, traceback
from pathlib import Path
from datetime import datetime

from sovereign_swarm.pipeline.schemas import PipelineLead, LeadStatus
from sovereign_swarm.pipeline.extractor import Extractor
from sovereign_swarm.pipeline.validator import validate
from sovereign_swarm.pipeline.enricher import enrich, enrich_and_route


# ─── Dead Letter Queue (failed leads) ──────────────────────────────
DLQ_DIR = Path("/tmp/dubai_re_dlq")
DLQ_DIR.mkdir(parents=True, exist_ok=True)

# ─── Stats ─────────────────────────────────────────────────────────
_stats = {"processed": 0, "valid": 0, "invalid": 0, "low_conf": 0, "errors": 0}


async def process_lead(lead: PipelineLead) -> dict:
    """
    Run the full 4-layer pipeline on one lead.
    Returns routing summary or error info.
    """
    try:
        lead.log_layer("worker", "started", {})

        # ── Layer 2: Extract ──────────────────────────────────────
        lead.extracted = Extractor.extract(lead.raw.raw_text)
        lead.status = LeadStatus.parsing
        lead.log_layer("extractor", "done", {
            "confidence": lead.extracted.confidence,
            "method": lead.extracted.extraction_method,
        })

        # ── Layer 3: Validate ─────────────────────────────────────
        lead.validated = validate(lead)
        if not lead.validated.is_valid:
            if lead.status == LeadStatus.invalid:
                _stats["invalid"] += 1
            else:
                _stats["low_conf"] += 1
            lead.log_layer("worker", "rejected", {
                "reason": lead.validated.validation_errors,
                "score": lead.validated.validation_score,
            })
            # Save to DLQ for review
            _save_dlq(lead)
            return {
                "lead_id": lead.lead_id,
                "status": lead.status.value,
                "valid": False,
                "errors": lead.validated.validation_errors,
                "score": lead.validated.validation_score,
            }

        _stats["valid"] += 1

        # ── Layer 4: Enrich + Route ───────────────────────────────
        result = enrich_and_route(lead)
        _stats["processed"] += 1
        return result

    except Exception as e:
        _stats["errors"] += 1
        lead.log_layer("worker", "exception", {"error": str(e), "trace": traceback.format_exc()[:500]})
        _save_dlq(lead)
        return {
            "lead_id": lead.lead_id,
            "status": "error",
            "valid": False,
            "error": str(e),
        }


def _save_dlq(lead: PipelineLead):
    """Dump failed lead to dead letter queue for human review."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    file = DLQ_DIR / f"{lead.lead_id}_{ts}.json"
    with open(file, "w") as f:
        json.dump({
            "lead_id": lead.lead_id,
            "status": lead.status.value,
            "raw": lead.raw.model_dump(),
            "extracted": lead.extracted.model_dump(),
            "validated": lead.validated.model_dump(),
            "history": lead.layer_history,
            "created_at": lead.created_at.isoformat(),
        }, f, indent=2, default=str)


# ─── Queue (asyncio version) ────────────────────────────────────────
_queue: asyncio.Queue = asyncio.Queue()

async def enqueue(lead: PipelineLead) -> str:
    """Add lead to queue. Returns lead_id immediately."""
    await _queue.put(lead)
    return lead.lead_id


async def worker_loop():
    """Run forever, processing leads from queue."""
    while True:
        lead = await _queue.get()
        try:
            await process_lead(lead)
        finally:
            _queue.task_done()


async def get_stats() -> dict:
    return dict(_stats)


# ─── Synchronous convenience (for FastAPI sync routes) ───────────────
def process_sync(raw_text: str, source: str = "web", source_id: str = "") -> dict:
    """Fire-and-forget: create PipelineLead and process immediately (blocking)."""
    from sovereign_swarm.pipeline.schemas import RawLead, LeadSource
    try:
        src = LeadSource(source)
    except ValueError:
        src = LeadSource.manual
    # Guard empty text
    if not raw_text or not raw_text.strip():
        return {
            "lead_id": f"LD-{int(datetime.utcnow().timestamp()*1000)}",
            "status": "invalid",
            "valid": False,
            "error": "Empty raw_text",
            "errors": ["Empty raw_text"],
            "score": 0.0,
        }
    raw = RawLead(raw_text=raw_text.strip(), source=src, source_id=source_id)
    lead = PipelineLead(raw=raw)
    # Run async in new event loop
    return asyncio.run(process_lead(lead))
