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

from github import Github

redis_client = None
github_client = None

async def process_push_events():
    while True:
        try:
            event = await redis_client.lpop("push_events")
            if not event:
                await asyncio.sleep(5)
                continue
            
            event_data = json.loads(event.decode('utf-8'))
            has_force_push = await github_client.is_force_push(event_data["repo"]["name"], event_data["payload"]["before"], event_data["payload"]["head"])
            
            print(event_data["repo"]["name"], has_force_push)
            
            await asyncio.sleep(0.1)
        except Exception as e:
            print("Error processing GitHub events:", e)
            await asyncio.sleep(5)
            
async def process_spam_events():
    while True:
        try:
            event = await redis_client.lpop("spam_events")
            if not event:
                await asyncio.sleep(5)
                continue
            
            event_data = json.loads(event.decode('utf-8'))
            spam_events = await github_client.detect_spam(event_data["repo"]["name"], event_data["created_at"])
            
            print(event_data["repo"]["name"], spam_events)
            
            await asyncio.sleep(0.1)
        except Exception as e:
            print("Error processing GitHub events:", e)
            await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, github_client
    load_dotenv()
    
    redis_client = Redis(host=os.getenv("REDIS_HOST"), port=os.getenv("REDIS_PORT"), db=0, decode_responses=False)
    github_client = Github()
    
    poll_github_events_task = asyncio.create_task(github_client.poll_github_events())
    process_push_events_task = asyncio.create_task(process_push_events())
    process_spam_events_task = asyncio.create_task(process_spam_events())
    yield
    poll_github_events_task.cancel()
    process_push_events_task.cancel()

app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"message": "Hello World"}