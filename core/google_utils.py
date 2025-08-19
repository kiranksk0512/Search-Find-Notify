import aiohttp
import re
import json
from bs4 import BeautifulSoup

async def extract_google_tokens_and_cookies():
    url = "https://www.google.com/about/careers/applications/jobs/results/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    }

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
        if "AF_dataServiceRequests" in script.text:
            match = re.search(r"AF_dataServiceRequests\s*=\s*{.*?'ds:1'\s*:\s*{[^}]*?id\s*:\s*'([^']+)'", script.text, re.DOTALL)
            if match:
                rpcids = match.group(1)
            else:
                print("❌ Couldn't extract rpcids from AF_dataServiceRequests")
            break

    # Extract f.sid, bl, at from WIZ_global_data
    f_sid = bl = at = None
    for script in scripts:
        if "WIZ_global_data" in script.text:
            json_match = re.search(r"WIZ_global_data\s*=\s*({.*?});", script.text, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    f_sid = data.get("FdrFJe")
                    bl = data.get("cfb2h")
                    at = data.get("SNlM0e")  # Optional
                except json.JSONDecodeError:
                    print("❌ Failed to parse WIZ_global_data JSON")
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
