import os
import json
import math
import time
import asyncio
import httpx


class Github:
    """
    GitHub API client for polling events and detecting incidents.
    
    Handles GitHub API rate limiting, exponential backoff, and ETags for
    efficient polling. Monitors public GitHub events to detect force pushes
    and spam activity.
    
    Attributes:
        base_delay (float): Base delay in seconds for exponential backoff (default: 60s)
        max_delay (float): Maximum delay in seconds between retries (default: 900s/15min)
        max_retries (int): Maximum number of retry attempts (default: 10)
        poll_interval (int): Interval in seconds between polling requests (default: 15s)
        ETag (str | None): ETag value from previous request for conditional requests
        attempts (int): Current number of retry attempts
    """
    def __init__(
        self, 
        base_delay: float = 60.0, # 1 minute
        max_delay: float = 15 * 60.0, # 15 minutes 
        max_retries: int = 10, # 10 attempts 
        poll_interval: int = 15 # 15 seconds
    ) -> None:
        """
        Initialize GitHub API client.
        
        Args:
            base_delay: Base delay for exponential backoff in seconds
            max_delay: Maximum delay between retries in seconds
            max_retries: Maximum number of retry attempts before giving up
            poll_interval: Time to wait between successful polls in seconds
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.poll_interval = poll_interval
        self.ETag = None
        self.attempts = 0
        
    def get_headers(self) -> dict:
        """
        Get HTTP headers for GitHub API requests.
        
        Returns:
            dict: Headers including Accept, API version, and authorization token
        """
        return {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}"
        }
        
    async def handle_retry_after(self, response: httpx.Response, retry_after: str) -> None:
        """
        Handle rate limiting with Retry-After header.
        
        Sleeps for the duration specified in the Retry-After header,
        with a minimum delay of 1 second.
        
        Args:
            response: HTTP response object
            retry_after: Retry-After header value in seconds
        """
        delay = int(math.ceil(float(retry_after)))
        print("Retry-After detected, sleeping for", delay, "seconds")
        await asyncio.sleep(max(1, delay))
        
        self.attempts += 1
        if self.attempts > self.max_retries:
            response.raise_for_status()
    
    async def handle_rate_limit_reset(self, response: httpx.Response, ratelimit_reset: str) -> None:
        """
        Handle rate limit reset by waiting until the reset time.
        
        Calculates the time until rate limit resets and sleeps until then,
        with a minimum delay of 1 second to avoid timing issues.
        
        Args:
            response: HTTP response object
            ratelimit_reset: Unix timestamp when rate limit resets
            
        Raises:
            ValueError: If ratelimit_reset cannot be parsed as a timestamp
        """
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
        """
        Implement exponential backoff for retries.
        
        Calculates delay based on number of attempts using the formula:
        delay = min(base_delay * (2 ^ attempts), max_delay)
        
        Increments the attempts counter and sleeps for the calculated duration.
        The delay doubles with each attempt up to the maximum delay.
        
        Example delays (base_delay=60s, max_delay=900s):
            - Attempt 1: 60s
            - Attempt 2: 120s
            - Attempt 3: 240s
            - Attempt 4: 480s
            - Attempt 5+: 900s (max)
        """
        delay = min(self.max_delay, self.base_delay * (2 ** self.attempts))
        print("Exponential backoff, sleeping for", delay, "seconds")
        await asyncio.sleep(delay)
        self.attempts += 1
        
    async def handle_error_codes(self, response: httpx.Response) -> bool:
        """
        Handle GitHub API error codes and rate limiting.
        
        Implements exponential backoff for rate limiting (403, 429) and
        server errors (500, 502, 503). Returns True if the request should
        be retried.
        
        Args:
            response: HTTP response object
            
        Returns:
            bool: True if request should be retried, False otherwise
            
        Raises:
            Exception: If max retries exceeded or unrecoverable error
        """
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


    async def is_force_push(self, repo_name: str, before_sha: str, after_sha: str, ref: str) -> bool:
        """
        Check if a push was forced by comparing commit SHAs.
        
        Uses GitHub's compare API to determine if commits diverged,
        indicating a force push occurred.
        
        Args:
            repo_name: Full repository name (e.g., "owner/repo")
            before_sha: Previous commit SHA
            after_sha: New commit SHA
            ref: Git reference (e.g., "refs/heads/main")
            
        Returns:
            bool: True if push was forced, False otherwise
        """
        if ref not in ("refs/heads/main", "refs/heads/master"):
            return False

        try:
            async with httpx.AsyncClient() as client:
                compare_url = f"https://api.github.com/repos/{repo_name}/compare/{before_sha}...{after_sha}"
                
                headers = self.get_headers()
                    
                response = await client.get(
                    compare_url,
                    headers=headers
                )
                
                if (await self.handle_error_codes(response)):
                    return False
                
                if response.status_code == 200:
                    compare_data = response.json()
                    return compare_data.get('status') in ['diverged', 'behind']
                
                return False
        except Exception as e:
            print(f"Error checking force push: {e}")
            return False
    
    async def detect_spam(self, repo_name: str, created_at: str) -> int:
        """
        Detect spam activity by tracking event frequency.
        
        Uses Redis sorted sets to track issue/PR creation events within
        a 10-minute sliding window. Returns count of recent events for
        the repository.
        
        Args:
            repo_name: Full repository name (e.g., "owner/repo")
            created_at: ISO 8601 timestamp of event creation
            
        Returns:
            int: Number of events in the last 10 minutes for this repo
        """
        from main import redis_client
        redis_key = f"spam_check:{repo_name}"
        timestamp = time.mktime(time.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ"))
        await redis_client.zadd(redis_key, {created_at: timestamp})
        
        cutoff_time = timestamp - 600
        await redis_client.zremrangebyscore(redis_key, 0, cutoff_time)
        await redis_client.expire(redis_key, 3600)
        
        recent_count = await redis_client.zcard(redis_key)
        
        return recent_count
    
    async def poll_github_events(self) -> None:
        """
        Continuously poll GitHub public events API.
        
        Fetches public GitHub events every poll_interval seconds and queues
        relevant events (PushEvent, IssuesEvent, PullRequestEvent) to Redis
        for processing. Uses ETags for efficient polling and handles rate
        limiting automatically.
        
        Queues:
            - push_events: All PushEvent events
            - issue_pr_events: IssuesEvent and PullRequestEvent (action=opened)
            
        Runs indefinitely as a background task.
        
        Raises:
            Exception: Logs errors and continues polling after delay
        """
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    headers = self.get_headers()
                
                    if self.ETag:
                        headers["If-None-Match"] = self.ETag
                    
                    response = await client.get(
                        "https://api.github.com/events",
                        headers=headers
                    )
                    
                    if (await self.handle_error_codes(response)):
                        continue
                    
                    self.attempts = 0
                    events = response.json()
                    for event in events:
                        from main import redis_client
                        if event["type"] == "PushEvent":
                            await redis_client.rpush("push_events", json.dumps(event))
                        if event["type"] in ["IssuesEvent", "PullRequestEvent"]:
                            action = event.get("payload", {}).get("action")
                            if action in ["opened", "reopened"]:
                                await redis_client.rpush("spam_events", json.dumps(event))
                        
                    await asyncio.sleep(self.poll_interval)
                except Exception as e:
                    print("Error polling GitHub events:", e)
