"""sovereign_swarm/pipeline/extractor.py — Layer 2: Extract + Fallback

Never trust the LLM alone. Regex catches what LLM misses.
Always returns ExtractedLead with every field set (defaults where needed).
"""
from __future__ import annotations

import re, json, os, urllib.request, socket
from typing import Optional

from sovereign_swarm.pipeline.schemas import ExtractedLead, Intent


# ─── Regex Patterns ──────────────────────────────────────────────────
PHONE_PATTERNS = [
    re.compile(r'\+971\s?5\d{1}\s?\d{3}\s?\d{4}'),     # +971 5X XXX XXXX
    re.compile(r'\+971\d{8,9}'),                          # +971XXXXXXXX
    re.compile(r'05\d{1}\s?\d{3}\s?\d{4}'),              # 05X XXX XXXX
    re.compile(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b'),   # fallback: any 10-digit
]

BUDGET_PATTERNS = [
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:million|M|mln)', re.I),
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:k|thousand)', re.I),
    re.compile(r'(?:budget|under|below|up to|max)\s*[AED]*\s*(\d+(?:,\d+)*)', re.I),
    re.compile(r'\b(\d{6,9})\b'),                        # Any 6-9 digit number = likely budget
]

BEDROOM_PATTERNS = [
    re.compile(r'\b(\d)\s*br\b', re.I),
    re.compile(r'\b(\d)\s*bedroom', re.I),
    re.compile(r'\bstudio\b', re.I),
    re.compile(r'\b(\d)\s*bed\b', re.I),
]

LOCATION_PATTERNS = [
    re.compile(r'\b(business\s+bay|marina|downtown|jlt|jumeirah|palm\s+jumeirah|damac\s+hills|al\s+barsha|dubai\s+hills|arabian\s+ranches)\b', re.I),
    re.compile(r'\bin\s+([A-Za-z\s]+?)(?:\s+(?:budget|under|for|with|and|looking|$))', re.I),
]

PROPERTY_TYPE_PATTERNS = [
    re.compile(r'\b(apartment|flat|villa|townhouse|penthouse|studio|duplex|loft)\b', re.I),
]

INTENT_PATTERNS = {
    Intent.buy: re.compile(r'\b(buy|purchase|invest|investment|own)\b', re.I),
    Intent.rent: re.compile(r'\b(rent|rental|lease|leasing)\b', re.I),
    Intent.sell: re.compile(r'\b(sell|selling|resell)\b', re.I),
    Intent.browse: re.compile(r'\b(look|looking|browse|browsing|explore|checking)\b', re.I),
}

URGENCY_PATTERNS = [
    re.compile(r'\b(urgent|asap|immediately|emergency|must move)\b', re.I),
    re.compile(r'\b(this week|next week|soon|quick)\b', re.I),
    re.compile(r'\b(browsing|checking|just looking|curious)\b', re.I),
]

# ─── Location Normalization ────────────────────────────────────────────
LOCATION_ALIASES = {
    "marina": "Dubai Marina",
    "business bay": "Business Bay",
    "downtown": "Downtown Dubai",
    "jlt": "Jumeirah Lakes Towers",
    "jvc": "Jumeirah Village Circle",
    "jvt": "Jumeirah Village Triangle",
    "al barsha": "Al Barsha",
    "barsha": "Al Barsha",
    "damac hills": "Damac Hills",
    "dubai hills": "Dubai Hills Estate",
    "arabian ranches": "Arabian Ranches",
    "palm": "Palm Jumeirah",
    "palm jumeirah": "Palm Jumeirah",
}

# ─── Groq LLM Stub (production uses actual SDK) ──────────────────────
def _call_llm_for_extraction(raw_text: str) -> dict:
    """Call Groq or fallback for structured extraction.
    In production this hits: https://api.groq.com/openai/v1/chat/completions
    """
    system_prompt = '''
You are a zero-tolerance extraction engine. Output ONLY valid JSON matching the schema below. No markdown, no explanation, no preamble.

Schema:
{
  "name": "",
  "phone": "",
  "email": "",
  "budget_min": 0,
  "budget_max": 0,
  "budget_currency": "AED",
  "location": "",
  "bedrooms": 0,
  "property_type": "",
  "intent": "buy|rent|invest|sell|browse|unknown",
  "urgency": "",
  "notes": "",
  "confidence": 0.0
}

Field rules:
- If field not found return "" or 0. Never invent.
- Budget: if user says "under 3 million" → budget_max: 3000000
- Phone: include country code (+971) if present, else raw number found
- Bedrooms: "2BR" → 2, "studio" → 0
- Intent: one of buy|rent|invest|sell|browse|unknown (default browse)
- Confidence: 0.0–1.0 based on how many fields were found (start at 0.0, +0.1 per field found, cap at 1.0)
'''

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return {}  # Will trigger regex fallback

    try:
        payload = json.dumps({
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "max_tokens": 512,
        }).encode()

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        socket.setdefaulttimeout(15)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            parsed["extraction_method"] = "llm"
            return parsed
    except Exception:
        return {}


# ─── Regex Extractors ────────────────────────────────────────────────
def _extract_phone(text: str) -> str:
    for pat in PHONE_PATTERNS:
        m = pat.search(text)
        if m:
            raw = m.group(0)
            digits = re.sub(r'\D', '', raw)
            # If starts with 971X (11 digits), format as +971X XXX XXXX
            if len(digits) == 11 and digits.startswith('971'):
                return f"+{digits[0:3]} {digits[3:4]} {digits[4:7]} {digits[7:11]}"
            if len(digits) == 10 and digits.startswith('05'):
                return f"+971 {digits[2:3]} {digits[3:6]} {digits[6:10]}"
            return raw
    return ""


def _extract_budget(text: str) -> tuple[int, int]:
    """Returns (min, max). Only max if that's all we found."""
    max_budget = 0
    min_budget = 0

    # "3 million"
    for m in re.finditer(r'(\d+(?:\.\d+)?)\s*(?:million|M|mln)', text, re.I):
        val = int(float(m.group(1)) * 1_000_000)
        if val > max_budget:
            max_budget = val

    # "120k"
    for m in re.finditer(r'(\d+(?:\.\d+)?)\s*(?:k|thousand)', text, re.I):
        val = int(float(m.group(1)) * 1000)
        if val > max_budget:
            max_budget = val

    # "under 3M" or "budget 3 million"
    m = re.search(r'(?:under|below|up to|max|budget)\s*[AED]*(?:\s*)?(\d+(?:\.\d+)?)\s*(?:million|M|mln)?', text, re.I)
    if m:
        val_str = m.group(1)
        if 'million' in text[m.start():m.end()].lower() or 'M' in text[m.start():m.end()].upper():
            val = int(float(val_str) * 1_000_000)
        else:
            val = int(float(val_str))
        if val > max_budget:
            max_budget = val

    # Any large number 100000+
    for m in re.finditer(r'\b(\d{6,9})\b', text):
        val = int(m.group(1))
        if 100000 <= val <= 500_000_000:
            if val > max_budget:
                max_budget = val

    return min_budget, max_budget


def _extract_bedrooms(text: str) -> int:
    m = re.search(r'\b(\d)\s*br\b', text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r'\b(\d)\s*bedroom', text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r'\b(\d)\s*bed\b', text, re.I)
    if m:
        return int(m.group(1))
    if re.search(r'\bstudio\b', text, re.I):
        return 0
    return 0


def _extract_location(text: str) -> str:
    # Try known areas
    for pat in LOCATION_PATTERNS:
        m = pat.search(text)
        if m:
            if 'in ' in text[m.start():m.end()].lower():
                return text[m.start()+3:m.end()].strip()
            return m.group(0).strip()
    # Fallback: "in X" pattern
    m = re.search(r'\bin\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)\b', text, re.I)
    if m:
        return m.group(1).strip()
    return ""


def _extract_property_type(text: str) -> str:
    for pat in PROPERTY_TYPE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).lower()
    return ""


def _extract_intent(text: str) -> Intent:
    """Score text against intent keywords, pick best."""
    scores: dict[str, int] = {
        "buy": 0, "rent": 0, "sell": 0, "invest": 0, "browse": 0, "unknown": 0,
    }
    # buy / invest
    if re.search(r'\b(buy|purchase|invest|investment|own|acquire)\b', text, re.I):
        scores["buy"] += 1
        scores["invest"] += 1
    # rent
    if re.search(r'\b(rent|rental|lease|leasing|tenant)\b', text, re.I):
        scores["rent"] += 1
    # sell
    if re.search(r'\b(sell|selling|resell|listing)\b', text, re.I):
        scores["sell"] += 1
    # browse
    if re.search(r'\b(look|looking|browse|browsing|explore|checking|curious)\b', text, re.I):
        scores["browse"] += 1

    best = max(scores.keys(), key=lambda k: scores[k])
    if scores[best] == 0:
        return Intent.browse
    try:
        return Intent(best)
    except ValueError:
        return Intent.browse


def _extract_urgency(text: str) -> str:
    hot = re.search(r'\b(urgent|asap|immediately|emergency|must move)\b', text, re.I)
    warm = re.search(r'\b(this week|next week|soon|quick)\b', text, re.I)
    cold = re.search(r'\b(browsing|checking|just looking|curious|sometime)\b', text, re.I)
    if hot:
        return "hot"
    if warm:
        return "warm"
    if cold:
        return "cold"
    return ""


def _normalize_location(raw: str) -> str:
    low = raw.lower().strip()
    for alias, canonical in LOCATION_ALIASES.items():
        if alias in low:
            return canonical
    return raw.title() if raw else ""


# ─── Confidence Scorer ───────────────────────────────────────────────
def _compute_confidence(extracted: ExtractedLead, raw_text: str) -> float:
    score = 0.0
    if extracted.name:
        score += 0.1
    if extracted.phone:
        score += 0.2
    if extracted.budget_max:
        score += 0.2
    if extracted.location:
        score += 0.2
    if extracted.bedrooms >= 0:
        score += 0.1
    if extracted.property_type:
        score += 0.1
    if extracted.intent != Intent.unknown:
        score += 0.05
    if extracted.urgency:
        score += 0.05
    # Boost if text length reasonable (too short = ambiguous)
    if len(raw_text) < 20:
        score *= 0.7
    return round(min(score, 1.0), 2)


# ─── Public API ──────────────────────────────────────────────────────
class Extractor:
    """Entry point for Layer 2. LLM + regex with guaranteed output."""

    @staticmethod
    def extract(raw_text: str) -> ExtractedLead:
        # Try LLM first
        llm_data = _call_llm_for_extraction(raw_text)

        # Build from LLM if available, else empty
        name = llm_data.get("name", "")
        phone = llm_data.get("phone", "")
        email = llm_data.get("email", "")
        budget_min = llm_data.get("budget_min", 0)
        budget_max = llm_data.get("budget_max", 0)
        budget_currency = llm_data.get("budget_currency", "AED")
        location = llm_data.get("location", "")
        bedrooms = llm_data.get("bedrooms", 0)
        property_type = llm_data.get("property_type", "")
        intent_str = llm_data.get("intent", "browse")
        urgency = llm_data.get("urgency", "")
        notes = llm_data.get("notes", "")
        confidence = llm_data.get("confidence", 0.0)
        extraction_method = llm_data.get("extraction_method", "")

        # Regex fallback for anything LLM missed
        if not phone:
            phone = _extract_phone(raw_text)
        if not budget_max:
            budget_min, budget_max = _extract_budget(raw_text)
        if not location:
            location = _extract_location(raw_text)
        if bedrooms == 0:
            bedrooms = _extract_bedrooms(raw_text)
        if not property_type:
            property_type = _extract_property_type(raw_text)
        if intent_str == "browse":
            intent = _extract_intent(raw_text)
        else:
            try:
                intent = Intent(intent_str)
            except ValueError:
                intent = Intent.browse
        if not urgency:
            urgency = _extract_urgency(raw_text)

        notes = notes or raw_text[:500]

        extracted = ExtractedLead(
            name=name,
            phone=phone,
            email=email,
            budget_min=budget_min,
            budget_max=budget_max,
            budget_currency=budget_currency,
            location=location,
            location_normalized=_normalize_location(location),
            bedrooms=bedrooms,
            property_type=property_type,
            intent=intent,
            urgency=urgency,
            notes=notes,
            confidence=confidence,
            extraction_method=extraction_method or "regex-fallback" if not llm_data else "llm+regex",
        )

        # Re-compute confidence (LLM might have wrong confidence)
        extracted.confidence = _compute_confidence(extracted, raw_text)

        return extracted
