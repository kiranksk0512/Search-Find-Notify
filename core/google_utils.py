import aiohttp
import re
import json
from bs4 import BeautifulSoup

async def extract_google_tokens_and_cookies():
    url = "https://www.google.com/about/careers/applications/jobs/results/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    }

    html = ""
    cookies_dict = {}
    raw_cookie_header = ""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            html = await response.text()
            cookies_dict = {c.key: c.value for c in response.cookies.values()}
            raw_cookie_header = "; ".join(f"{c.key}={c.value}" for c in response.cookies.values())

    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script")

    # Extract rpcids from AF_dataServiceRequests
    rpcids = None
    for script in scripts:
        txt = script.string or script.text or ""
        if "AF_dataServiceRequests" not in txt:
            continue
        m = re.search(
            r"AF_dataServiceRequests\s*=\s*{.*?'ds:1'\s*:\s*{[^}]*?id\s*:\s*'([^']+)'",
            txt,
            re.DOTALL,
        )
        if m:
            rpcids = m.group(1)
        break

    # Extract f.sid (FdrFJe), bl (cfb2h), at (SNlM0e) from WIZ_global_data
    f_sid = bl = at = None
    for script in scripts:
        txt = script.string or script.text or ""
        if "WIZ_global_data" not in txt:
            continue
        m = re.search(r"WIZ_global_data\s*=\s*({.*?});", txt, re.DOTALL)
        if not m:
            continue
        blob = m.group(1)
        data = None
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            # Tolerate single quotes / unquoted keys
            blob2 = re.sub(r"(\w+)\s*:", r'"\1":', blob)
            blob2 = blob2.replace("'", '"')
            data = json.loads(blob2)
        f_sid = (data or {}).get("FdrFJe")
        bl = (data or {}).get("cfb2h")
        at = (data or {}).get("SNlM0e")
        break

    print("📌 Extracted Tokens:")
    print(f"  • rpcids : {rpcids}")
    print(f"  • f.sid  : {f_sid}")
    print(f"  • bl     : {bl}")
    print(f"  • at     : {at}")

    print("\n🍪 Extracted Cookies:")
    for k, v in cookies_dict.items():
        print(f"  • {k} = {v}")

    print(f"\n📦 Raw Cookie Header:\n  {raw_cookie_header}")

    return {
        "rpcids": rpcids,
        "f.sid": f_sid,
        "bl": bl,
        "at": at,
        "cookies": cookies_dict,
        "cookie_header": raw_cookie_header,
    }
