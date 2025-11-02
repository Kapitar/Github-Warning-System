import os
import math
import time
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio
import httpx
from redis.asyncio import Redis
from dotenv import load_dotenv

from pprint import pprint

redis = None

async def is_force_push(repo_name: str, before_sha: str, after_sha: str) -> bool:
    try:
        async with httpx.AsyncClient() as client:
            compare_url = f"https://api.github.com/repos/{repo_name}/compare/{before_sha}...{after_sha}"
            response = await client.get(
                compare_url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
                }
            )
            
            if response.status_code == 200:
                compare_data = response.json()
                return compare_data.get('status') in ['diverged', 'behind']
            
            return False
    except Exception as e:
        print(f"Error checking force push: {e}")
        return False


async def process_github_events():
    while True:
        try:
            event = await redis.lpop("push_events")
            if not event:
                await asyncio.sleep(5)
                continue
            
            event_data = json.loads(event.decode('utf-8'))
            has_force_push = await is_force_push(event_data["repo"]["name"], event_data["payload"]["before"], event_data["payload"]["head"])
            
            # print(event_data["repo"]["name"], has_force_push)
            
            await asyncio.sleep(0.1)
        except Exception as e:
            print("Error processing GitHub events:", e)
            await asyncio.sleep(5)


async def poll_github_events():
    ETag = None
    poll_interval = 15
    attempts = 0
    max_retries = 10
    base_delay = 60.0 # 1 minute
    max_delay = 15 * 60.0 # 15 minutes
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                headers = {
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
                }
                if ETag:
                    headers["If-None-Match"] = ETag
                
                response = await client.get(
                    "https://api.github.com/events",
                )
                
                if response.status_code in (403, 429):
                    retry_after = response.headers.get("retry-after")
                    if retry_after:
                        delay = int(math.ceil(float(retry_after)))
                        await asyncio.sleep(max(1, delay))
                        attempts += 1
                        if attempts > max_retries:
                            response.raise_for_status()
                        continue
                    
                    ratelimit_remaining = response.headers.get("x-ratelimit-remaining")
                    ratelimit_reset = response.headers.get("x-ratelimit-reset")
                    if ratelimit_remaining == "0" and ratelimit_reset:
                        try:
                            reset_epoch = int(ratelimit_reset)
                            now = time.time()
                            delay = max(0, reset_epoch - now)
                            await asyncio.sleep(delay)

                            attempts += 1
                            if attempts > max_retries:
                                response.raise_for_status()
                            continue
                        except ValueError:
                            print("Error parsing rate limit reset time")
                            pass
                    
                    if attempts >= max_retries:
                        response.raise_for_status()
                        continue

                    delay = min(max_delay, base_delay * (2 ** attempts))
                    await asyncio.sleep(delay) 
                    attempts += 1
                    continue

                if response.status_code == 304:
                    poll_interval = int(response.headers.get("X-Poll-Interval", poll_interval))
                    await asyncio.sleep(poll_interval)
                    continue
                
                events = response.json()
                for event in events:
                    if event["type"] == "PushEvent":
                        await redis.rpush("push_events", json.dumps(event))
                    
                await asyncio.sleep(poll_interval)
            except Exception as e:
                print("Error polling GitHub events:", e)
    

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis
    load_dotenv()
    
    redis = Redis(host=os.getenv("REDIS_HOST"), port=os.getenv("REDIS_PORT"), db=0, decode_responses=False)
    poll_github_events_task = asyncio.create_task(poll_github_events())
    process_github_events_task = asyncio.create_task(process_github_events())
    yield
    poll_github_events_task.cancel()
    process_github_events_task.cancel()

app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"message": "Hello World"}