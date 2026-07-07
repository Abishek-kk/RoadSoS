import asyncio

import httpx

from app.main import app


async def main() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/chat",
            json={
                "messages": [
                    {"role": "user", "content": "tell the top 2 hospital in my location"}
                ],
                "lat": 12.9715,
                "lng": 80.0430,
            },
        )
    print(response.text)


asyncio.run(main())
