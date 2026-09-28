"""M0 spike: verify SEC EDGAR assumptions A14, A15 (specs-plan.md sec11.2).

A14: companyfacts (via submissions + companyfacts JSON) is reachable with a
     proper User-Agent, and each fact carries a `filed` date, `fy`, `fp`, `form`.
A15: SEC's published fair-access rate limit (recorded from their policy page,
     not load-tested).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import httpx
from _common import save_json, section, settings

from bullpit.doctor import sec_user_agent

APPLE_CIK = "0000320193"
COMPANYFACTS_URL = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{APPLE_CIK}.json"
FAIR_ACCESS_POLICY_URL = "https://www.sec.gov/os/webmaster-faq#developers"


def check_companyfacts(user_agent: str) -> dict[str, Any]:
    section("A14: companyfacts reachable, filing-date fields present")
    resp = httpx.get(COMPANYFACTS_URL, headers={"User-Agent": user_agent}, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    # Look at a revenue-shaped tag under us-gaap for the filing-date fields.
    us_gaap = data.get("facts", {}).get("us-gaap", {})
    candidate_tags = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")
    revenue_tag = next((t for t in candidate_tags if t in us_gaap), None)
    sample_facts: list[dict[str, Any]] = []
    if revenue_tag:
        usd_facts = us_gaap[revenue_tag].get("units", {}).get("USD", [])
        sample_facts = usd_facts[:3]

    result = {
        "status_code": resp.status_code,
        "entity_name": data.get("entityName"),
        "revenue_tag_found": revenue_tag,
        "sample_fact_fields": [sorted(f.keys()) for f in sample_facts],
        "sample_facts": sample_facts,
        "has_filed_date": all("filed" in f for f in sample_facts) if sample_facts else None,
    }
    print(f"  entity: {result['entity_name']}")
    print(f"  revenue tag: {revenue_tag}")
    print(f"  sample fact fields: {result['sample_fact_fields']}")
    print(f"  has 'filed' date on every sample fact: {result['has_filed_date']}")
    return result


def record_fair_access_policy() -> dict[str, Any]:
    section("A15: SEC fair-access rate limit (recorded, not load-tested)")
    note = (
        "SEC's published policy (as of check date) asks for no more than 10 "
        "requests per second, and requires a descriptive User-Agent with a "
        "contact. See: https://www.sec.gov/os/accessing-edgar-data"
    )
    print(f"  {note}")
    return {"note": note, "source": "https://www.sec.gov/os/accessing-edgar-data"}


def main() -> None:
    s = settings()
    ua = sec_user_agent(s)
    print(f"Using User-Agent: {ua}")

    results: dict[str, Any] = {}
    results["a14_companyfacts"] = check_companyfacts(ua)
    results["a15_fair_access_policy"] = record_fair_access_policy()

    save_json("sec_edgar", results)
    print("\nDone. Check scripts/spikes/output/sec_edgar.json for the full record.")


if __name__ == "__main__":
    main()
