import aiohttp
from django.conf import settings


async def yelp_search_api(params, timeout=3):
    async with aiohttp.ClientSession(conn_timeout=timeout) as session:
        async with session.get(
            "https://api.yelp.com/v3/businesses/search",
            headers={"Authorization": f"Bearer {settings.YELP_SECRET}"},
            params=params,
        ) as response:
            return await response.json()


async def yelp_business_api(business_id, timeout=3):
    async with aiohttp.ClientSession(conn_timeout=timeout) as session:
        async with session.get(
            f"https://api.yelp.com/v3/businesses/{business_id}",
            headers={"Authorization": f"Bearer {settings.YELP_SECRET}"},
        ) as response:
            return await response.json()
