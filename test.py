import aiohttp
import asyncio

async def test_netflix_request():
    url = "https://explore.jobs.netflix.net/api/apply/v2/jobs"
    params = [
        ('domain', 'netflix.com'),
        ('start', '20'),
        ('num', '10'),
        ('exclude_pid', '790304512952'),
        ('location', 'United States'),
        ('pid', '790304512952'),
        ('Teams', 'Data%20%26%20Insights'),
        ('Teams', 'Engineering%20Operations'),
        ('Teams', 'Product%20Design'),
        ('Teams', 'Engineering'),
        ('domain', 'netflix.com'),
        ('sort_by', 'new'),
    ]

    headers = {
        'accept': '*/*',
        'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
        'cache-control': 'no-cache',
        'content-type': 'application/json',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': 'https://explore.jobs.netflix.net/careers?location=United%20States&pid=790304512952&Teams=Data%20%26%20Insights&Teams=Engineering%20Operations&Teams=Product%20Design&Teams=Engineering&domain=netflix.com&sort_by=new',
        'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    }

    cookies = {
        '_vs': '5713247805614038662:1753924480.3745198:6958606098770403143',
        '_vscid': '3',
        '_ga': 'GA1.1.1570927973.1753924481',
        '_ga_8XHF9J4KQ8': 'GS2.1.s1753924481$o1$g1$t1753926603$j60$l0$h0',
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params, cookies=cookies) as resp:
            print(f"Status: {resp.status}")
            text = await resp.text()
            print(f"Response (first 500 chars):\n{text[:500]}")

asyncio.run(test_netflix_request())
