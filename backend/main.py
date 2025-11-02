import os
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
            
            print(event_data["repo"]["name"], has_force_push)
            
            await asyncio.sleep(0.1)
        except Exception as e:
            print("Error processing GitHub events:", e)
            await asyncio.sleep(5)


async def poll_github_events():
    async with httpx.AsyncClient() as client:
        while True:
            try:
                response = await client.get(
                    "https://api.github.com/events",
                    headers = {
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                        "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
                    }
                )
                
                events = response.json()
                for event in events:
                    if event["type"] == "PushEvent":
                        await redis.rpush("push_events", json.dumps(event))
                    
                await asyncio.sleep(15)
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