import os
import math
import time
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import httpx
from redis.asyncio import Redis
from dotenv import load_dotenv
from pprint import pprint

import database
import llm
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
            has_force_push = await github_client.is_force_push(event_data["repo"]["name"], event_data["payload"]["before"], event_data["payload"]["head"], event_data["payload"]["ref"])
            
            print(event_data["repo"]["name"], has_force_push)
            if has_force_push:
                print("FORCE_PUSH: ", event_data)
                summary = await llm.generate_force_push_summary(event_data)
                await database.save_event_summary(event_data, summary)
                print("Saved summary:", summary)
            
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
            if (spam_events >= 3):
                print("SUS ACTIVITY: ", event_data)
                summary = await llm.generate_activity_spike_summary(event_data)
                await database.save_event_summary(event_data, summary)
                print("Saved summary:", summary)
            
            await asyncio.sleep(0.1)
        except Exception as e:
            print("Error processing GitHub events:", e)
            await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, github_client
    load_dotenv()
    
    await database.init_db()
    await llm.init_llm()
    
    redis_client = Redis(host=os.getenv("REDIS_HOST"), port=os.getenv("REDIS_PORT"), db=0, decode_responses=False)
    github_client = Github()
    
    poll_github_events_task = asyncio.create_task(github_client.poll_github_events())
    process_push_events_task = asyncio.create_task(process_push_events())
    process_spam_events_task = asyncio.create_task(process_spam_events())
    yield
    poll_github_events_task.cancel()
    process_push_events_task.cancel()
    process_spam_events_task.cancel()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True, 
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/summary")
async def get_summaries(since: int):
    summaries = await database.get_event_summaries(since, limit=100000, offset=0)
    return summaries


@app.get("/stream")
async def stream_summaries():
    async def event_generator():        
        while True:
            summaries = await database.get_event_summaries(0, limit=50, offset=0)
            
            for summary in summaries:
                data = json.dumps({
                    "id": summary.id,
                    "payload": summary.payload,
                    "summary": summary.summary,
                    "created_at": summary.created_at.isoformat()
                })
                yield f"data: {data}\n\n"            
            await asyncio.sleep(5)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )