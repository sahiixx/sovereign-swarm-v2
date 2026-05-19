"""sovereign_swarm/pipeline/schemas.py — Bulletproof lead ingestion schemas.

4-layer pipeline: Ingress → Extract → Validate → Enrich → Route
Every field has defaults. Nothing is nullable without intent.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────
class LeadSource(StrEnum):
    telegram = "telegram"
    whatsapp = "whatsapp"
    web = "web"
    voice = "voice"
    scraper = "scraper"
    manual = "manual"


class LeadStatus(StrEnum):
    raw = "raw"                 # Layer 1: just captured
    parsing = "parsing"         # Layer 2: LLM extracting
    valid = "valid"             # Layer 3: passed validation
    low_confidence = "low_confidence"
    invalid = "invalid"
    enriched = "enriched"       # Layer 4: enriched
    routed = "routed"


class Intent(StrEnum):
    buy = "buy"
    rent = "rent"
    invest = "invest"
    sell = "sell"
    browse = "browse"
    unknown = "unknown"


# ──────────────────────────────────────────────────────────────────
# Layer 1: Raw Ingress (never lose data)
class RawLead(BaseModel):
    """Absolute minimum — store this before doing ANYTHING."""
    raw_text: str = Field(min_length=1, description="Original text exactly as received")
    source: LeadSource = LeadSource.manual
    source_id: str = ""                      # chat_id, phone, session_id
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    raw_metadata: dict = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────
# Layer 2: Extracted (LLM + regex)
class ExtractedLead(BaseModel):
    """Fields the LLM + regex managed to pull out."""
    name: str = ""
    phone: str = ""
    email: str = ""
    budget_min: int = 0
    budget_max: int = 0
    budget_currency: str = "AED"
    location: str = ""
    location_normalized: str = ""            # "Marina" → "Dubai Marina"
    bedrooms: int = 0
    property_type: str = ""                    # apartment|villa|penthouse|studio
    intent: Intent = Intent.unknown
    urgency: str = ""
    notes: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    extraction_method: str = ""                # "llm", "regex", "llm+regex", "fallback"


# ──────────────────────────────────────────────────────────────────
# Layer 3: Validated (gatekeeper)
class ValidatedLead(BaseModel):
    """After hard constraint checks."""
    is_valid: bool = False
    validation_errors: list[str] = Field(default_factory=list)
    validation_score: float = 0.0            # 0–1 weighted score
    missing_required: list[str] = Field(default_factory=list)
    has_contact: bool = False                # phone OR source_id present
    has_location_or_intent: bool = False


# ──────────────────────────────────────────────────────────────────
# Layer 4: Enriched + Routed
class EnrichedLead(BaseModel):
    """Final form ready for CRM + routing."""
    lead_id: str = ""
    agent_name: str = "Sahil Khan"
    agent_phone: str = "+971585476077"
    agent_rera: str = "15970"
    wa_outreach_link: str = ""
    tg_notification_sent: bool = False
    crm_file_path: str = ""
    search_results: list[dict] = Field(default_factory=list)
    routed_at: Optional[datetime] = None


# ──────────────────────────────────────────────────────────────────
# 🎯 MASTER: Full pipeline record
class PipelineLead(BaseModel):
    """One record that travels through all 4 layers + tracks history."""
    # Identity
    lead_id: str = Field(default_factory=lambda: f"LD-{int(datetime.utcnow().timestamp()*1000)}")
    status: LeadStatus = LeadStatus.raw
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Layer outputs (each layer appends its result)
    raw: RawLead
    extracted: ExtractedLead = Field(default_factory=ExtractedLead)
    validated: ValidatedLead = Field(default_factory=ValidatedLead)
    enriched: EnrichedLead = Field(default_factory=EnrichedLead)

    # Audit trail
    layer_history: list[dict] = Field(default_factory=list)
    retries: int = 0
    max_retries: int = 3

    def log_layer(self, layer: str, action: str, detail: dict | None = None):
        self.layer_history.append({
            "layer": layer,
            "action": action,
            "timestamp": datetime.utcnow().isoformat(),
            "detail": detail or {},
        })
        self.updated_at = datetime.utcnow()

    def to_crm(self) -> dict:
        """Flatten to CRM-ready JSON."""
        return {
            "lead_id": self.lead_id,
            "status": self.status.value,
            "name": self.extracted.name,
            "phone": self.extracted.phone,
            "email": self.extracted.email,
            "budget_min": self.extracted.budget_min,
            "budget_max": self.extracted.budget_max,
            "location": self.extracted.location_normalized or self.extracted.location,
            "bedrooms": self.extracted.bedrooms,
            "property_type": self.extracted.property_type,
            "intent": self.extracted.intent.value,
            "urgency": self.extracted.urgency,
            "confidence": self.extracted.confidence,
            "has_contact": self.validated.has_contact,
            "validation_score": self.validated.validation_score,
            "wa_link": self.enriched.wa_outreach_link,
            "tg_sent": self.enriched.tg_notification_sent,
            "search_count": len(self.enriched.search_results),
            "created_at": self.created_at.isoformat(),
            "history": self.layer_history,
        }
