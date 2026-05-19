"""sovereign_swarm/pipeline/enricher.py — Layer 4: Enrich + Route

Takes validated leads, runs property search, generates outreach links,
saves CRM, sends Telegram. Nothing leaks through unhandled.
"""
from __future__ import annotations

import json, urllib.parse
from pathlib import Path
from datetime import datetime

from sovereign_swarm.pipeline.schemas import PipelineLead, EnrichedLead, LeadStatus
from sovereign_swarm.agents.dubai_re_agent import DubaiREAgent
from sovereign_swarm.campaigns.lead_router import LeadRouter


# ─── Singletons ─────────────────────────────────────────────────────
_agent: DubaiREAgent | None = None
_router: LeadRouter | None = None

def _get_agent():
    global _agent
    if _agent is None:
        _agent = DubaiREAgent()
    return _agent

def _get_router():
    global _router
    if _router is None:
        _router = LeadRouter()
    return _router


# ─── Enrichment ─────────────────────────────────────────────────────
def enrich(lead: PipelineLead) -> EnrichedLead:
    """Search properties, build outreach, prepare CRM."""
    agent = _get_agent()
    extracted = lead.extracted

    # Build search query
    parts = []
    if extracted.bedrooms > 0:
        parts.append(f"{extracted.bedrooms} bedroom")
    if extracted.property_type:
        parts.append(extracted.property_type)
    if extracted.location:
        parts.append(f"in {extracted.location}")
    if extracted.budget_max:
        parts.append(f"budget {extracted.budget_max}")

    query = " ".join(parts) or extracted.notes or "property in Dubai"

    # Run search
    try:
        search_result = agent.handle_voice_query(query)
    except Exception as e:
        lead.log_layer("enricher", "search_failed", {"error": str(e)})
        search_result = {"results": [], "results_count": 0, "lead": {"qualified": False, "confidence": 0}}

    # Generate WhatsApp outreach link
    wa_link = ""
    if extracted.phone:
        wa_msg = (
            f"Hi {extracted.name or 'there'}, this is Sahil Khan from FAM Real Estate. "
            f"I saw your interest in {extracted.location or 'Dubai properties'}. "
            f"I found {search_result.get('results_count', 0)} options. Can we discuss?"
        )
        clean = extracted.phone.replace("+", "").replace(" ", "").replace("-", "")
        wa_link = f"https://wa.me/{clean}?text={urllib.parse.quote(wa_msg[:300])}"

    lead.log_layer("enricher", "enriched", {
        "search_count": search_result.get("results_count", 0),
        "wa_link": bool(wa_link),
    })

    lead.status = LeadStatus.enriched

    return EnrichedLead(
        lead_id=lead.lead_id,
        wa_outreach_link=wa_link,
        search_results=search_result.get("results", []),
    )


# ─── Routing ────────────────────────────────────────────────────────
def route(lead: PipelineLead) -> dict:
    """Save CRM + send Telegram. Returns routing summary."""
    router = _get_router()
    extracted = lead.extracted
    enriched = lead.enriched

    # Save CRM
    crm_data = lead.to_crm()
    crm_dir = Path("/tmp/dubai_re_crm")
    crm_dir.mkdir(parents=True, exist_ok=True)
    crm_file = crm_dir / f"{lead.lead_id}.json"
    with open(crm_file, "w") as f:
        json.dump(crm_data, f, indent=2, default=str)

    # Telegram notification
    tg_ok = False
    if extracted.phone:
        wa_msg = (
            f"Hi {extracted.name or 'there'}, this is Sahil Khan from FAM Real Estate. "
            f"I saw your interest in {extracted.location or 'Dubai properties'}. I'd love to help!"
        )
        clean = extracted.phone.replace("+", "").replace(" ", "").replace("-", "")
        wa_link = f"https://wa.me/{clean}?text={urllib.parse.quote(wa_msg[:300])}"

        card = (
            f"🔥 *NEW {extracted.urgency.upper() if extracted.urgency else 'LEAD'}*\n\n"
            f"👤 *{extracted.name or 'Unknown'}*\n"
            f"📞 `{extracted.phone}`\n"
            f"💰 Budget: AED {extracted.budget_max:,}" if extracted.budget_max else "💰 Budget: N/A" + "\n"
            f"🏠 {extracted.bedrooms}BR {extracted.property_type} in {extracted.location}\n"
            f"📝 {extracted.notes[:200]}\n\n"
            f"📊 Score: {int(extracted.confidence*100)}% | Intent: {extracted.intent.value}\n"
            f"💬 [WhatsApp Lead]({wa_link})\n"
            f"🆔 `{lead.lead_id}`"
        )

        resp = router._tg_api("sendMessage", {
            "chat_id": router.chat_id,
            "text": card,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        })
        tg_ok = resp.get("ok", False)

    lead.enriched.tg_notification_sent = tg_ok
    lead.enriched.crm_file_path = str(crm_file)
    lead.enriched.routed_at = datetime.utcnow()
    lead.status = LeadStatus.routed

    lead.log_layer("router", "routed", {
        "crm_file": str(crm_file),
        "telegram_sent": tg_ok,
        "wa_link": enriched.wa_outreach_link,
    })

    return {
        "lead_id": lead.lead_id,
        "status": lead.status.value,
        "crm": str(crm_file),
        "telegram": tg_ok,
        "wa_link": enriched.wa_outreach_link,
        "search_count": len(enriched.search_results),
    }


# ─── Full pipeline convenience ──────────────────────────────────────
def enrich_and_route(lead: PipelineLead) -> dict:
    """Layer 4 complete: enrich then route."""
    lead.enriched = enrich(lead)
    return route(lead)
