import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio
import httpx
from redis.asyncio import Redis
from dotenv import load_dotenv

from pprint import pprint

redis = None


async def poll_github_events():
    async with httpx.AsyncClient() as client:
        while True:
            try:
                response = await client.get(
                    "https://api.github.com/events",
                    headers = {
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28" 
                    }
                )
                
                pprint(response.json())
                await asyncio.sleep(15)
            except Exception as e:
                print("Error polling GitHub events:", e)
    

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis
    load_dotenv()
    
    task = asyncio.create_task(poll_github_events())
    redis = Redis(host=os.getenv("REDIS_HOST"), port=os.getenv("REDIS_PORT"), db=0, decode_responses=False)
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"message": "Hello World"}