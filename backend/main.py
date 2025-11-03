import os
import math
import time
import random
from datetime import datetime, timedelta
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
    """
    Process GitHub PushEvents from Redis queue to detect force pushes.
    
    Continuously polls the 'push_events' Redis queue for new push events.
    For each event, checks if it was a force push to main/master branch.
    If a force push is detected:
    - Retrieves historical force push accidents for the repository
    - Generates an AI summary of the incident
    - Saves the summary and records the accident in the database
    
    Runs indefinitely as a background task.
    
    Raises:
        Exception: Logs any errors and continues processing after 5s delay
    """
    while True:
        try:
            event = await redis_client.lpop("push_events")
            if not event:
                await asyncio.sleep(5)
                continue
            
            event_data = json.loads(event.decode('utf-8'))
            has_force_push = await github_client.is_force_push(event_data["repo"]["name"], event_data["payload"]["before"], event_data["payload"]["head"], event_data["payload"]["ref"])
            
            # print(event_data["repo"]["name"], has_force_push)
            if has_force_push:
                print("FORCE_PUSH: ", event_data)
                accidents = await database.get_accidents("force_push", event_data["repo"]["name"])
                summary = await llm.generate_force_push_summary(event_data, accidents)
                await database.save_event_summary(event_data, summary)
                await database.save_accident("force_push", event_data["repo"]["name"])
                print("Saved summary:", summary)
            
            await asyncio.sleep(0.1)
        except Exception as e:
            print("Error processing GitHub events:", e)
            await asyncio.sleep(5)
            
async def process_spam_events():
    """
    Process GitHub issue/PR events from Redis queue to detect spam activity.
    
    Continuously polls the 'spam_events' Redis queue for new issue/PR creation events.
    For each event:
    - Detects if there's suspicious activity (multiple events in short timeframe)
    - Records the accident in the database
    - If spam threshold is exceeded (≥1 suspicious events):
      * Retrieves recent issue creation accidents from last 24 hours
      * Generates an AI summary of the activity spike
      * Saves the summary to the database
    
    Runs indefinitely as a background task.
    
    Raises:
        Exception: Logs any errors and continues processing after 5s delay
    """
    while True:
        try:
            event = await redis_client.lpop("spam_events")
            if not event:
                await asyncio.sleep(5)
                continue
            
            event_data = json.loads(event.decode('utf-8'))
            spam_events = await github_client.detect_spam(event_data["repo"]["name"], event_data["created_at"])
            
            print(event_data["repo"]["name"], spam_events)
            await database.save_accident("issue_created", event_data["repo"]["name"])
            if (spam_events >= 1):
                print("SUS ACTIVITY: ", event_data)
                accidents = await database.get_accidents("issue_created", event_data["repo"]["name"], hours=24)
                summary = await llm.generate_activity_spike_summary(event_data, accidents)
                await database.save_event_summary(event_data, summary)
                print("Saved summary:", summary)
            
            await asyncio.sleep(0.1)
        except Exception as e:
            print("Error processing GitHub events:", e)
            await asyncio.sleep(5)

async def generate_synthetic_data():
    """
    Generate synthetic GitHub events for testing.
    
    Creates fake PushEvents, IssuesEvents, and PullRequestEvents with
    realistic data structure and queues them to Redis for processing.
    """
    
    repos = [
        "test-org/repo-1",
        "test-org/repo-2",
        "user/project-alpha",
        "company/backend-service"
    ]
    
    users = ["alice", "bob", "charlie", "dave"]
    
    # Generate spam/issue events
    spam_repo = random.choice(repos)
    for i in range(10):  # Generate burst of issues
        event = {
            "id": f"synthetic-issue-{i}",
            "type": "IssuesEvent",
            "actor": {
                "id": 12345,
                "login": "spammer",
                "avatar_url": "https://avatars.githubusercontent.com/u/1?",
                "url": "https://api.github.com/users/spammer"
            },
            "repo": {
                "id": random.randint(100000, 999999),
                "name": spam_repo,
                "url": f"https://api.github.com/repos/{spam_repo}"
            },
            "payload": {
                "action": "opened",
                "issue": {
                    "id": random.randint(100000, 999999),
                    "number": i + 1,
                    "title": f"Test issue {i}",
                    "body": "This is a test issue",
                    "html_url": f"https://github.com/{spam_repo}/issues/{i+1}"
                }
            },
            "public": True,
            "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        
        await redis_client.rpush("spam_events", json.dumps(event))
        print(f"Generated issue event #{i+1} for {spam_repo}")
    
    print("\n✅ Synthetic data generation complete!")
    print(f"- Generated 5 force push events")
    print(f"- Generated 10 issue events for spam detection")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, github_client
    load_dotenv()
    
    await database.init_db()
    await llm.init_llm()
    
    redis_client = Redis(host=os.getenv("REDIS_HOST"), port=os.getenv("REDIS_PORT"), db=0, decode_responses=False)
    github_client = Github()
    
    await generate_synthetic_data()
    
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
    """
    Get event summaries created after a specific timestamp.
    
    Retrieves all event summaries that were created after the provided
    Unix timestamp. Useful for fetching historical data or catching up
    on missed events.
    
    Args:
        since: Unix timestamp (seconds since epoch). Returns all summaries
               created after this time. Use 0 to get all summaries.
    
    Returns:
        list[EventSummary]: List of event summaries ordered by creation time (newest first)
    
    Example:
        GET /summary?since=1699000000
        GET /summary?since=0  # Get all summaries
    """
    summaries = await database.get_event_summaries(since, limit=100000, offset=0)
    return summaries


@app.get("/details")
async def get_repo_details(repo_name: str, accident_type: str):
    """
    Get detailed information about a specific repository.
    
    Retrieves the most recent event summary and all force push accidents
    for the specified repository.
    
    Args:
        repo_name: Full repository name (e.g., "owner/repo")
        accident_type: Type of accident to filter (e.g., "force_push" or "issue_created")
    
    Returns:
        dict: Contains:
            - summary: Most recent EventSummary or None
            - accidents: List of Accident objects for force pushes
    
    Example:
        GET /details?repo_name=owner/repo
    """
    summary = await database.get_event_summaries_by_repo(repo_name)
    accidents = await database.get_accidents(accident_type, repo_name)
    return {
        "summary": summary,
        "accidents": accidents
    }


@app.get("/stream")
async def stream_summaries():
    """
    Stream event summaries in real-time using Server-Sent Events (SSE).
    
    Establishes a persistent connection that pushes new event summaries
    to the client as they are created. On initial connection, sends all
    historical summaries, then only new ones going forward.
    
    The stream sends data in SSE format:
        data: {"id": 1, "payload": {...}, "summary": "...", "created_at": "..."}
    
    Returns:
        StreamingResponse: SSE stream with media type "text/event-stream"
    
    Headers:
        - Cache-Control: no-cache
        - Connection: keep-alive
        - X-Accel-Buffering: no
    
    Example:
        GET /stream
        
        Client usage:
        const eventSource = new EventSource('/stream');
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log(data);
        };
    """
    async def event_generator():
        last_check = 0
        sent_ids = set()
        
        while True:
            summaries = await database.get_event_summaries(last_check, limit=50, offset=0)
            
            for summary in summaries:
                if summary.id in sent_ids:
                    continue
                
                data = json.dumps({
                    "id": summary.id,
                    "payload": summary.payload,
                    "summary": summary.summary,
                    "created_at": summary.created_at.isoformat()
                })
                yield f"data: {data}\n\n"
                sent_ids.add(summary.id)
                
            if summaries:
                last_check = int(max(s.created_at.timestamp() for s in summaries)) + 1
                            
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