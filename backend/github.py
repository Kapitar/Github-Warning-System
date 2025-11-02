import os
import redis
import json
import math
import time
import asyncio
import httpx


class Github:
    def __init__(
        self, 
        base_delay: float = 60.0, # 1 minute
        max_delay: float = 15 * 60.0, # 15 minutes 
        max_retries: int = 10, # 10 attempts 
        poll_interval: int = 15 # 15 seconds
    ) -> None:
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.poll_interval = poll_interval
        self.ETag = None
        self.attempts = 0
        
    def get_headers(self) -> dict:
        return {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
        }
        
    async def handle_retry_after(self, response: httpx.Response, retry_after: str) -> None:
        delay = int(math.ceil(float(retry_after)))
        print("Retry-After detected, sleeping for", delay, "seconds")
        await asyncio.sleep(max(1, delay))
        
        self.attempts += 1
        if self.attempts > self.max_retries:
            response.raise_for_status()
    
    async def handle_rate_limit_reset(self, response: httpx.Response, ratelimit_reset: str) -> None:
        try:
            reset_epoch = int(ratelimit_reset)
            now = time.time()
            delay = max(0, reset_epoch - now)
            print("Rate limit exceeded, sleeping until reset in", delay, "seconds")
            await asyncio.sleep(delay)

            self.attempts += 1
            if self.attempts > self.max_retries:
                response.raise_for_status()
        except ValueError:
            print("Error parsing rate limit reset time")
            pass
        
    async def handle_exponential_backoff(self) -> None:
        delay = min(self.max_delay, self.base_delay * (2 ** self.attempts))
        print("Exponential backoff, sleeping for", delay, "seconds")
        await asyncio.sleep(delay)
        self.attempts += 1
        
    async def handle_error_codes(self, response: httpx.Response) -> bool:
        if response.status_code in (403, 429):
            retry_after = response.headers.get("retry-after")
            if retry_after:
                await self.handle_retry_after(response, retry_after)
                return True
            
            ratelimit_remaining = response.headers.get("x-ratelimit-remaining")
            ratelimit_reset = response.headers.get("x-ratelimit-reset")
            if ratelimit_remaining == "0" and ratelimit_reset:
                await self.handle_rate_limit_reset(response, ratelimit_reset)
                return True
            
            if self.attempts >= self.max_retries:
                response.raise_for_status()
                return True

            await self.handle_exponential_backoff()
            return True

        if response.status_code == 304:
            self.poll_interval = int(response.headers.get("X-Poll-Interval", self.poll_interval))
            await asyncio.sleep(self.poll_interval)
            return True
        
        return False

    async def poll_github_events(self) -> None:
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    headers = self.get_headers()
                
                    if self.ETag:
                        headers["If-None-Match"] = self.ETag
                    
                    response = await client.get(
                        "https://api.github.com/events",
                    )
                    
                    if (await self.handle_error_codes(response)):
                        continue
                    
                    self.attempts = 0
                    events = response.json()
                    for event in events:
                        if event["type"] == "PushEvent":
                            await redis.rpush("push_events", json.dumps(event))
                        
                    await asyncio.sleep(self.poll_interval)
                except Exception as e:
                    print("Error polling GitHub events:", e)
