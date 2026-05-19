"""Dubai Real Estate Voice Agent — Specialist agent for Sovereign Swarm DSL.
End-to-end: voice input → intent parsing → property search → lead qualification → notification.
"""
import json, os, re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class PropertySearch:
    bedrooms: Optional[int] = None
    location: str = ""
    budget_max: Optional[int] = None  # AED
    property_type: str = ""  # apartment, villa, townhouse
    area_min: Optional[int] = None  # sqft
    area_max: Optional[int] = None
    furnished: Optional[bool] = None
    ready_status: str = ""  # ready, off-plan
    amenities: List[str] = None
    def __post_init__(self):
        if self.amenities is None:
            self.amenities = []

@dataclass
class LeadProfile:
    confidence: float = 0.0
    urgency: str = ""  # immediate, soon, browsing
    budget_indicated: bool = False
    preferred_contact: str = ""  # phone, whatsapp, email
    intent: str = ""  # buy, rent, invest, sell
    qualified: bool = False

class DubaiREAgent:
    """Dubai Real Estate Specialist Agent."""
    
    # Dubai market data — enriched from Prypco profile of Sahil Khan (RERA 15970)
    LOCATIONS = {
        "dubai marina": {"avg_price_sqft": 1800, "type": "premium"},
        "downtown dubai": {"avg_price_sqft": 2500, "type": "luxury"},
        "jbr": {"avg_price_sqft": 1700, "type": "premium"},
        "palm jumeirah": {"avg_price_sqft": 3000, "type": "luxury"},
        "jlt": {"avg_price_sqft": 1400, "type": "mid"},
        "business bay": {"avg_price_sqft": 1600, "type": "mid"},
        "damac hills": {"avg_price_sqft": 1200, "type": "mid"},
        "arabian ranches": {"avg_price_sqft": 1100, "type": "family"},
        "meydan": {"avg_price_sqft": 1500, "type": "premium"},
        # Real expertise areas from Prypco profile
        "jebel ali village": {"avg_price_sqft": 900, "type": "family"},
        "rak central": {"avg_price_sqft": 800, "type": "emerging"},
        "al barari": {"avg_price_sqft": 1300, "type": "green"},
        "emirates hills": {"avg_price_sqft": 2200, "type": "luxury"},
        "dubai land": {"avg_price_sqft": 850, "type": "offplan"},
        "al marjan island": {"avg_price_sqft": 950, "type": "offplan"},
        "dubai investment park": {"avg_price_sqft": 750, "type": "mid"},
        "tecom": {"avg_price_sqft": 1400, "type": "mid"},
    }
    
    AMENITIES_MAP = {
        "pool": ["pool", "swimming pool", "lap pool", "infinity pool"],
        "gym": ["fitness center", "gym", "health club"],
        "parking": ["covered parking", "underground parking"],
        "security": ["24/7 security", "concierge", "gated"],
        "beach": ["private beach", "beach access"],
        "golf": ["golf course view", "golf community"],
        "metro": ["near metro", "metro access"],
    }

    def __init__(self):
        self.listings_db: List[dict] = []  # Would connect to live DLD/broker feed
        self.agent_profile = {
            "name": "Sahil Khan",
            "rera": "15970",
            "brokerage": "F A M REAL ESTATE BROKER L.L.C",
            "services": ["Mortgage", "Golden Visa", "Property Advisory", "Holiday Homes", "Expat Finance"],
            "contact": {
                "whatsapp": "+971585476077",
                "mobile": "+971585476077",
                "agency": "+971567148469",
                "instagram": "sahiix.ai",
                "telegram": "Zeus920",
            },
            "bio": "Dubai Investment & Mortgage Consultant | Property Advisor | Holiday Homes | Expat & Non-Resident Finance | ROI-focused property investments",
        }
        self._load_stub_listings()
        
    def _load_stub_listings(self):
        """Live listings scraped from Prypco profile of Sahil Khan (RERA 15970)."""
        self.listings_db = [
            # Original stubs (kept for testing)
            {"id": "DM001", "location": "dubai marina", "bedrooms": 2, "area_sqft": 1200, "price_aed": 2400000, "type": "apartment", "ready": True, "amenities": ["pool", "gym", "metro"]},
            {"id": "DM002", "location": "dubai marina", "bedrooms": 3, "area_sqft": 1800, "price_aed": 3800000, "type": "apartment", "ready": True, "amenities": ["pool", "gym", "parking", "beach"]},
            {"id": "DB001", "location": "downtown dubai", "bedrooms": 1, "area_sqft": 900, "price_aed": 2000000, "type": "apartment", "ready": True, "amenities": ["gym", "metro"]},
            {"id": "DB002", "location": "downtown dubai", "bedrooms": 2, "area_sqft": 1400, "price_aed": 3500000, "type": "apartment", "ready": False, "amenities": ["pool", "gym", "parking", "security"]},
            {"id": "PJ001", "location": "palm jumeirah", "bedrooms": 4, "area_sqft": 3500, "price_aed": 12000000, "type": "villa", "ready": True, "amenities": ["pool", "gym", "beach", "security"]},
            {"id": "JLT001", "location": "jlt", "bedrooms": 2, "area_sqft": 1100, "price_aed": 1600000, "type": "apartment", "ready": True, "amenities": ["pool", "metro"]},
            {"id": "BB001", "location": "business bay", "bedrooms": 1, "area_sqft": 850, "price_aed": 1300000, "type": "apartment", "ready": False, "amenities": ["gym", "parking"]},
            {"id": "AR001", "location": "arabian ranches", "bedrooms": 4, "area_sqft": 3200, "price_aed": 4200000, "type": "villa", "ready": True, "amenities": ["pool", "golf", "security"]},
            # ─── LIVE PRYPCO LISTINGS (scraped 2025-05-19) ───
            {"id": "PR001", "location": "dubai land", "bedrooms": 1, "area_sqft": 600, "price_aed": 2301850, "type": "apartment", "ready": False, "amenities": ["pool", "beach"], "project": "Damac Islands - Maldives 3", "handover": "Q4 2029"},
            {"id": "PR002", "location": "dubai land", "bedrooms": 3, "area_sqft": 1800, "price_aed": 6850000, "type": "villa", "ready": False, "amenities": ["pool", "gym", "beach", "security"], "project": "Damac Islands - Maldives 5", "handover": "Q4 2029"},
            {"id": "PR003", "location": "dubai land", "bedrooms": 2, "area_sqft": 900, "price_aed": 3450000, "type": "apartment", "ready": False, "amenities": ["pool", "gym"], "project": "Damac Islands - Maldives 1", "handover": "Q4 2029"},
            {"id": "PR004", "location": "dubai land", "bedrooms": 1, "area_sqft": 650, "price_aed": 2277440, "type": "apartment", "ready": False, "amenities": ["pool", "gym"], "project": "Damac Islands - Maldives 2", "handover": "Q4 2029"},
            {"id": "PR005", "location": "dubai land", "bedrooms": 1, "area_sqft": 620, "price_aed": 2204160, "type": "apartment", "ready": False, "amenities": ["pool", "beach"], "project": "Damac Islands - Bora Bora 1", "handover": "Q4 2029"},
            {"id": "PR006", "location": "dubai land", "bedrooms": 1, "area_sqft": 580, "price_aed": 2138450, "type": "apartment", "ready": False, "amenities": ["pool", "gym"], "project": "Damac Islands - Fiji 1", "handover": "Q4 2029"},
            {"id": "PR007", "location": "dubai land", "bedrooms": 1, "area_sqft": 500, "price_aed": 2144000, "type": "apartment", "ready": False, "amenities": ["pool", "beach"], "project": "Damac Islands - Bora Bora 2", "handover": "Q4 2029"},
            {"id": "PR008", "location": "business bay", "bedrooms": 2, "area_sqft": 1100, "price_aed": 2700000, "type": "apartment", "ready": True, "amenities": ["gym", "parking", "security"], "project": "The Residences at Business Central", "handover": "Q2 2013"},
            {"id": "PR009", "location": "dubai land", "bedrooms": 2, "area_sqft": 950, "price_aed": 2750000, "type": "apartment", "ready": False, "amenities": ["pool", "gym", "beach"], "project": "DAMAC Islands 2 - Bahamas 1", "handover": "Q2 2030"},
            {"id": "PR010", "location": "dubai land", "bedrooms": 1, "area_sqft": 600, "price_aed": 2213500, "type": "apartment", "ready": False, "amenities": ["pool", "gym"], "project": "Damac Islands - Fiji 2", "handover": "Q4 2029"},
            {"id": "PR011", "location": "dubai land", "bedrooms": 1, "area_sqft": 630, "price_aed": 2341000, "type": "apartment", "ready": False, "amenities": ["pool", "beach"], "project": "Damac Islands - Maldives 4", "handover": "Q4 2029"},
            {"id": "PR012", "location": "dubai investment park", "bedrooms": 2, "area_sqft": 900, "price_aed": 2450000, "type": "apartment", "ready": False, "amenities": ["pool", "gym"], "project": "DAMAC Riverside - Lush", "handover": "Q4 2027"},
            {"id": "PR013", "location": "tecom", "bedrooms": 2, "area_sqft": 950, "price_aed": 2510000, "type": "apartment", "ready": False, "amenities": ["pool", "gym", "security"], "project": "Damac Casa", "handover": "Q4 2026"},
            {"id": "PR014", "location": "al marjan island", "bedrooms": 2, "area_sqft": 1000, "price_aed": 2550000, "type": "apartment", "ready": False, "amenities": ["pool", "beach", "gym"], "project": "Mondrian Al Marjan Island Beach Residences", "handover": "Q4 2028"},
            {"id": "PR015", "location": "business bay", "bedrooms": 2, "area_sqft": 1050, "price_aed": 2590000, "type": "apartment", "ready": True, "amenities": ["gym", "parking", "security"], "project": "The Vogue", "handover": "Q4 2014"},
            {"id": "PR016", "location": "dubai marina", "bedrooms": 2, "area_sqft": 1100, "price_aed": 3135000, "type": "apartment", "ready": True, "amenities": ["pool", "gym", "beach", "metro"], "project": "Damac Heights", "handover": "Q2 2018"},
        ]

    def parse_query(self, query: str) -> PropertySearch:
        """Parse natural language query into structured search."""
        q_lower = query.lower()
        search = PropertySearch()
        
        # Bedrooms
        bed_match = re.search(r'(\d+)\s*(?: bedroom| bed|br|bhk)', q_lower)
        if bed_match:
            search.bedrooms = int(bed_match.group(1))
        elif "studio" in q_lower:
            search.bedrooms = 0
        
        # Location
        for loc in self.LOCATIONS:
            if loc in q_lower:
                search.location = loc
                break
        # Also check for partial matches
        if not search.location:
            loc_hints = {
                "marina": "dubai marina",
                "downtown": "downtown dubai",
                "jbr": "jbr",
                "palm": "palm jumeirah",
                "jlt": "jlt",
                "business bay": "business bay",
                "damac": "damac hills",
                "arabian ranches": "arabian ranches",
                "ranches": "arabian ranches",
                "meydan": "meydan",
                # New Prypco areas
                "jebel ali": "jebel ali village",
                "rak": "rak central",
                "barari": "al barari",
                "emirates hills": "emirates hills",
                "dubai land": "dubai land",
                "marjan": "al marjan island",
                "investment park": "dubai investment park",
                "tecom": "tecom",
            }
            for hint, full in loc_hints.items():
                if hint in q_lower:
                    search.location = full
                    break
        
        # Budget
        budget_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:million|m\b|mil)', q_lower)
        if budget_match:
            search.budget_max = int(float(budget_match.group(1)) * 1000000)
        else:
            budget_match = re.search(r'(\d{6,})\s*aed', q_lower)
            if budget_match:
                search.budget_max = int(budget_match.group(1))
        
        # Property type
        if any(w in q_lower for w in ["villa", "villas"]):
            search.property_type = "villa"
        elif any(w in q_lower for w in ["townhouse", "town house", "townhome"]):
            search.property_type = "townhouse"
        elif any(w in q_lower for w in ["apartment", "flat", "condo"]):
            search.property_type = "apartment"
        
        # Ready / off-plan
        if "off-plan" in q_lower or "off plan" in q_lower or "future" in q_lower:
            search.ready_status = "off-plan"
        elif "ready" in q_lower or "handover" in q_lower:
            search.ready_status = "ready"
        
        # Amenities
        for keyword, variants in self.AMENITIES_MAP.items():
            for v in variants:
                if v in q_lower:
                    search.amenities.append(keyword)
                    break
        
        search.amenities = list(set(search.amenities))
        return search

    def search(self, params: PropertySearch) -> List[dict]:
        """Filter listings by search params."""
        results = []
        for listing in self.listings_db:
            match = True
            if params.bedrooms is not None and listing["bedrooms"] != params.bedrooms:
                match = False
            if params.location and listing["location"] != params.location:
                match = False
            # Budget match with tolerance — allow 20% above budget for premium queries
            if params.budget_max:
                tolerance = params.budget_max * 1.2
                if listing["price_aed"] > tolerance:
                    match = False
            if params.property_type and listing["type"] != params.property_type:
                match = False
            if params.ready_status and listing.get("ready") != (params.ready_status == "ready"):
                match = False
            if params.amenities:
                for am in params.amenities:
                    if am not in listing.get("amenities", []):
                        match = False
            if match:
                results.append(listing)
        
        # Sort by relevance (price closest to budget if provided)
        if params.budget_max:
            results.sort(key=lambda x: abs(x["price_aed"] - params.budget_max * 0.8))
        return results

    def qualify_lead(self, query: str, results: List[dict]) -> LeadProfile:
        """Score the buyer based on query depth and results match."""
        profile = LeadProfile()
        q_lower = query.lower()
        
        # Budget indicated = higher confidence
        if re.search(r'\d+\s*million|\d{6,}', q_lower):
            profile.budget_indicated = True
            profile.confidence += 0.3
        
        # Specific location = higher confidence
        if any(loc in q_lower for loc in self.LOCATIONS):
            profile.confidence += 0.2
        
        # Amenities specified = higher confidence
        if any(kw in q_lower for kw in ["pool", "gym", "parking", "beach"]):
            profile.confidence += 0.2
        
        # Urgency signals
        if any(w in q_lower for w in ["urgent", "asap", "this week", "immediately"]):
            profile.urgency = "immediate"
            profile.confidence += 0.2
        elif any(w in q_lower for w in ["soon", "next month", "looking"]):
            profile.urgency = "soon"
            profile.confidence += 0.1
        else:
            profile.urgency = "browsing"
        
        # Intent determination
        if any(w in q_lower for w in ["buy", "purchase", "invest"]):
            profile.intent = "buy"
        elif any(w in q_lower for w in ["rent", "lease", "monthly"]):
            profile.intent = "rent"
        elif any(w in q_lower for w in ["sell", "listing my"]):
            profile.intent = "sell"
        else:
            profile.intent = "explore"  # default
        
        # Qualified threshold
        profile.qualified = profile.confidence >= 0.5 and profile.budget_indicated
        profile.confidence = min(profile.confidence, 1.0)
        return profile

    def format_results(self, results: List[dict], lead: LeadProfile) -> str:
        """Format property results for voice/SMS/chat delivery."""
        if not results:
            return "No properties found matching your criteria. Try broadening your search."
        
        lines = []
        lines.append(f"Found {len(results)} properties for you.")
        if lead.qualified:
            lines.append(f"Lead score: {int(lead.confidence * 100)}% — you're a qualified buyer!")
        lines.append("")
        
        for r in results[:5]:
            price_m = r["price_aed"] / 1000000
            lines.append(f"ID {r['id']}: {r['bedrooms']}BR {r['type']} in {r['location'].title()}")
            lines.append(f"  {r['area_sqft']:,} sq ft | AED {price_m:.1f}M | Ready: {'Yes' if r.get('ready') else 'No'}")
            lines.append(f"  Amenities: {', '.join(r.get('amenities',[]))}")
            lines.append("")
        
        return "\n".join(lines)

    def handle_voice_query(self, transcript: str) -> dict:
        """End-to-end: voice transcript → result payload."""
        search = self.parse_query(transcript)
        results = self.search(search)
        lead = self.qualify_lead(transcript, results)
        formatted = self.format_results(results, lead)
        
        return {
            "ok": True,
            "search_params": {
                "bedrooms": search.bedrooms,
                "location": search.location,
                "budget_max": search.budget_max,
                "type": search.property_type,
                "ready": search.ready_status,
                "amenities": search.amenities,
            },
            "results_count": len(results),
            "results": results[:5],
            "lead": {
                "qualified": lead.qualified,
                "confidence": round(lead.confidence, 2),
                "urgency": lead.urgency,
                "intent": lead.intent,
            },
            "message": formatted,
        }

    def handle_text_query(self, text: str) -> str:
        """Text interface — returns formatted string."""
        result = self.handle_voice_query(text)
        return result["message"]


def main():
    agent = DubaiREAgent()
    
    # Test queries
    test_queries = [
        "2 bedroom apartment in Dubai Marina with pool and gym budget 3 million",
        "studio in Business Bay",
        "villa in Palm Jumeirah with beach access",
        "3 bedroom off-plan in JLT near metro",
    ]
    
    for q in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {q}")
        print(f"{'='*60}")
        print(agent.handle_text_query(q))


if __name__ == "__main__":
    main()
