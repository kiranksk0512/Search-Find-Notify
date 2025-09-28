# oracle_categories_helper.py
import random, time, requests
from urllib.parse import urlencode, quote

API_URL = "https://eeho.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
LOCATION_ID_USA = 300000000149325

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
]


def _headers():
    return {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://careers.oracle.com",
        "Referer": "https://careers.oracle.com/",
        "User-Agent": random.choice(USER_AGENTS),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def _get(params, retries=3, backoff=0.6):
    url = f"{API_URL}?{urlencode(params, doseq=True, quote_via=quote)}"
    for attempt in range(1, retries + 1):
        try:
            print(f"[oracle_categories_helper] GET {url} (attempt {attempt}/{retries})")
            r = requests.get(API_URL, headers=_headers(), params=params, timeout=30)
            if r.status_code == 200:
                print(f"[oracle_categories_helper] ✅ 200 OK, length={len(r.text)} chars")
                return r.json()
            else:
                print(f"[oracle_categories_helper] ❌ HTTP {r.status_code}")
        except Exception as e:
            print(f"[oracle_categories_helper] ⚠️ Exception on attempt {attempt}: {e}")
        time.sleep(backoff * attempt)
    print("[oracle_categories_helper] ❌ All retries failed, returning None")
    return None


def _finder_seed_primary(limit=1, offset=0) -> str:
    return (
        "findReqs;"
        "siteNumber=CX_45001,"
        "facetsList=LOCATIONS;WORK_LOCATIONS;WORKPLACE_TYPES;TITLES;CATEGORIES;ORGANIZATIONS;POSTING_DATES;FLEX_FIELDS,"
        "lastSelectedFacet=CATEGORIES,"
        f"selectedLocationsFacet={LOCATION_ID_USA},"
        f"limit={limit},offset={offset}"
    )


def _finder_seed_backup(limit=1, offset=0) -> str:
    return (
        "findReqs;"
        "siteNumber=CX_45001,"
        "facetsList=CATEGORIES,"
        "lastSelectedFacet=CATEGORIES,"
        f"selectedLocationsFacet={LOCATION_ID_USA},"
        f"limit={limit},offset={offset}"
    )


def _fetch_categories_facet():
    common = {
        "onlyData": "true",
        "expand": (
            "requisitionList.workLocation,"
            "requisitionList.otherWorkLocations,"
            "requisitionList.secondaryLocations,"
            "flexFieldsFacet.values,"
            "requisitionList.requisitionFlexFields"
        ),
    }

    # --- Try primary finder first ---
    print("[oracle_categories_helper] === Seed categories (PRIMARY) ===")
    p = dict(common, finder=_finder_seed_primary())
    data = _get(p)
    items = (data or {}).get("items") or []
    cats = (items[0] if items else {}).get("categoriesFacet") or []
    if cats:
        print(f"[oracle_categories_helper] PRIMARY categoriesFacet count={len(cats)}")
        return cats

    # --- Fallback to backup finder ---
    print("[oracle_categories_helper] === Seed categories (BACKUP) ===")
    b = dict(common, finder=_finder_seed_backup())
    data = _get(b)
    items = (data or {}).get("items") or []
    cats = (items[0] if items else {}).get("categoriesFacet") or []
    print(f"[oracle_categories_helper] BACKUP categoriesFacet count={len(cats)}")
    return cats


def resolve_category_ids(names: list[str]) -> list[int]:
    """
    Given category display names, return the matching Oracle facet IDs.
    Unknown names are ignored.
    """
    cats = _fetch_categories_facet()
    name_to_id = {c.get("Name"): c.get("Id") for c in cats if c.get("Id")}
    print("[oracle_categories_helper] All categories (name → id):")
    for n, i in name_to_id.items():
        print(f" - {n} → {i}")

    resolved = [name_to_id[n] for n in names if n in name_to_id]
    print(f"[oracle_categories_helper] Requested {names} → resolved IDs {resolved}")
    return resolved
