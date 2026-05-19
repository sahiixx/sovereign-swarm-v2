"""sovereign_swarm/pipeline/validator.py — Layer 3: Gatekeeper

Hard constraints. No mercy. Rejects bad leads before they pollute CRM.
"""
from __future__ import annotations

from sovereign_swarm.pipeline.schemas import PipelineLead, ValidatedLead, LeadStatus


# ─── Weights for validation scoring ─────────────────────────────────
WEIGHTS = {
    "phone": 0.30,
    "email": 0.10,
    "budget": 0.20,
    "location": 0.20,
    "bedrooms": 0.10,
    "intent": 0.10,
}

MIN_CONFIDENCE = 0.40       # Below this → low_confidence
MIN_SCORE = 0.35            # Below this → invalid
MIN_CONTACT_SCORE = 0.30    # Need at least phone OR chat_id


def validate(lead: PipelineLead) -> ValidatedLead:
    """
    Run gatekeeper rules on extracted data.
    Returns ValidatedLead with is_valid, errors, and weighted score.
    """
    errors: list[str] = []
    score = 0.0
    missing: list[str] = []
    extracted = lead.extracted

    # ─── Contact check ──────────────────────────────────────────────
    has_phone = bool(extracted.phone.strip())
    has_email = bool(extracted.email.strip())
    has_chat_id = bool(lead.raw.source_id.strip())
    has_contact = has_phone or has_email or has_chat_id

    if not has_contact:
        errors.append("No contact method (phone, email, or chat_id)")
        missing.append("phone or chat_id")
    else:
        if has_phone:
            score += WEIGHTS["phone"]
        elif has_email:
            score += WEIGHTS["email"] * 0.5
        if has_chat_id:
            score += 0.15

    # ─── Location or intent ─────────────────────────────────────────
    has_location = bool(extracted.location.strip())
    has_intent = extracted.intent.value != "unknown"
    has_loc_or_intent = has_location or has_intent

    if not has_loc_or_intent:
        errors.append("No location or intent specified")
        missing.append("location or intent")
    else:
        if has_location:
            score += WEIGHTS["location"]
        if has_intent:
            score += WEIGHTS["intent"]

    # ─── Budget ─────────────────────────────────────────────────────
    has_budget = extracted.budget_max > 0 or extracted.budget_min > 0
    if has_budget:
        score += WEIGHTS["budget"]
    else:
        missing.append("budget")

    # ─── Bedrooms ───────────────────────────────────────────────────
    has_beds = extracted.bedrooms >= 0  # studio = 0 is valid
    if has_beds or extracted.property_type == "studio":
        score += WEIGHTS["bedrooms"]
    else:
        missing.append("bedrooms")

    # ─── Confidence gate ────────────────────────────────────────────
    if extracted.confidence < MIN_CONFIDENCE:
        errors.append(f"Confidence {extracted.confidence:.2f} < minimum {MIN_CONFIDENCE}")

    # ─── Normalize score ──────────────────────────────────────────
    # If lots of text but low extraction, boost slightly
    raw_len = len(lead.raw.raw_text)
    if raw_len > 80 and score < 0.5:
        score += 0.05

    score = round(min(score, 1.0), 2)

    # ─── Final verdict ────────────────────────────────────────────
    is_valid = has_contact and has_loc_or_intent and score >= MIN_SCORE

    # Determine status
    if not is_valid:
        if not has_contact:
            lead.status = LeadStatus.invalid
        elif score < MIN_SCORE or extracted.confidence < MIN_CONFIDENCE:
            lead.status = LeadStatus.low_confidence
        else:
            lead.status = LeadStatus.invalid
    else:
        lead.status = LeadStatus.valid

    lead.log_layer("validator", "checked", {
        "is_valid": is_valid,
        "score": score,
        "errors": errors,
        "missing": missing,
    })

    return ValidatedLead(
        is_valid=is_valid,
        validation_errors=errors,
        validation_score=score,
        missing_required=missing,
        has_contact=has_contact,
        has_location_or_intent=has_loc_or_intent,
    )
