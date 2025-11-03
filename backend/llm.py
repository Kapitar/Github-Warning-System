import os
from openai import OpenAI

client = None

async def init_llm():
    global client
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
    )


force_push_instructions = """
You are an incident summarizer for GitHub PushEvents that involve force-pushes.

INPUTS:
- event_payload: a GitHub PushEvent JSON object.
- accidents: a JSON array of historical accident objects for this repo.
  Each object may contain:
    id (int|None), accident_type (str), timestamp (ISO-8601), repo_name (str).

GOAL:
Analyze the current PushEvent and the historical force-push accident data for the same repository.
Detect temporal, frequency, and correlation patterns, then summarize the incident concisely.

DATA SOURCES:
- Branch = event_payload.ref (strip "refs/heads/").
- Actor = event_payload.actor.login (fallback: event_payload.pusher.name or payload.sender.login).
- SHAs = event_payload.before and event_payload.after.
- The event itself is known to be a force-push.
- From accidents, include only those where:
    accident_type == "force_push" and repo_name matches the event’s repo (case-insensitive).

PATTERN ANALYSIS GUIDELINES:

1. **Recency Metrics**
   - c1h, c24h, c7d: counts of force-pushes within the last 1h, 24h, and 7d.
   - delta_prev: time since the previous force-push (in hours).

2. **Temporal Patterns**
   - Identify if force-pushes tend to cluster at specific times:
     * “daily bursts” → force-pushes occur at roughly the same hour each day.
     * “weekly pattern” → repeated bursts on same weekdays.
   - Detect “increasing trend” (e.g., 3→5→8 events per day over last 3 days).
   - Detect “quiet-to-burst” transitions (e.g., no activity 2d → sudden burst today).

3. **Correlation Patterns**
   - Compare today’s push time to previous ones: are they spaced by roughly 24h? → daily pattern.
   - Check if multiple bursts occur during working hours → human-driven.
   - If bursts occur at night/weekends → automated or CI behavior likely.

4. **Spike Heuristics**
   - If c1h ≥ 3 → “burst”.
   - If c24h ≥ 10 → “spike”.
   - If 3 or more consecutive days had ≥5 events → “persistent pattern”.

5. **Impact Assessment**
   - Force-push rewrites history, can cause pull errors, lost commits, broken references.
   - High frequency or consistent bursts imply automation risk or unstable CI.
   - If branch is “main” or “master”, emphasize criticality.

6. **Remediation Recommendations**
   - Notify maintainers and audit affected commit range.
   - Temporarily restrict branch permissions.
   - Enforce branch protection and status checks.
   - Investigate automation or scripts causing repeated force-pushes.
   - Educate contributors or add policy enforcement hooks.

OUTPUT FORMAT (STRICT):
- Output MUST be a raw JSON array, not a string.
- No escape characters (\\n, \\").
- No code fences.
- 3–5 items total.
- Each item under 25 words.
- Combine root cause, impact, detected temporal/correlation patterns, and next steps.
- Always include actor, branch, and SHAs if available.

EXAMPLES:

Example A:
["Force-push on main by @alice (27dcd146 → 6d7fce94).",
 "History rewrite; 4 force-pushes in 24h (burst).",
 "Pattern: daily bursts around 10:00 for past 3 days.",
 "Likely manual sync or rebase loop.",
 "Lock branch; enable branch protection and audit automation."]

Example B:
["Force-push on feature/login by @devsmith (a12b3c → e98f7d).",
 "Low immediate risk; only 2 force-pushes this week.",
 "But 3 consecutive Fridays show similar bursts — weekly trend.",
 "Investigate CI rebase behavior; enforce PR checks.",
 "Add automated branch protection."]

Example C:
["Force-push on dev by @ci-bot (6b21e → 8af0d).",
 "Detected spike: 12 force-pushes/24h; previous week average 2/day.",
 "Bursts at midnight daily → automated job correlation.",
 "Investigate CI misconfiguration; throttle workflows.",
 "Temporarily disable force-push permission."]

Now analyze event_payload and accidents, then output ONLY the raw JSON array as specified above.
"""


async def generate_force_push_summary(payload: dict):
    response = client.responses.create(
        model="gpt-4o",
        instructions=force_push_instructions,
        input=str(payload),
    )
    return response.output_text


activity_spike_instructions = """
You are an incident summarizer for newly opened GitHub Issues and Pull Requests.

INPUTS:
- event_payload: JSON payload of either an IssuesEvent (action="opened") or PullRequestEvent (action="opened").
- accidents: JSON ARRAY of recent GitHub event payloads (similar shape to PushEvent objects), possibly mixed types.
  Each element may be an IssuesEvent, PullRequestEvent, or other events. Timestamps may appear as
  created_at / timestamp / event.created_at.

GOAL:
Summarize the CURRENT event and assess patterns from accidents LIMITED TO: issues opened within the last 24 hours.
(We still identify the current event type—Issue or PR—but pattern metrics are computed from Issues opened in 24h.)

HOW TO PARSE:
- Event type:
  * If event_payload.type == "IssuesEvent" and action == "opened" → "Issue opened".
  * If event_payload.type == "PullRequestEvent" and action == "opened" → "Pull Request opened".
- Actor: prefer event_payload.actor.login; fallback to sender.login; else pusher.name; else "unknown".
- Repository: prefer repository.full_name; else repo.name; else "unknown".
- Number & title:
  * Issue: issue.number and issue.title
  * PR: pull_request.number and pull_request.title
- Time fields for accidents: prefer created_at; else timestamp; else use top-level "created_at" if present.
- For 24h window, compare accidents’ timestamps to event_payload timestamp (or "now" if missing).

FILTERING FOR PATTERNS:
- From accidents, KEEP ONLY those that are IssuesEvent with action="opened" AND within the last 24 hours for the SAME repository as event_payload (case-insensitive match on repository.full_name / repo.name).
- Define issues_last_24h = count of those filtered accidents.
- Also compute:
  * unique_reporters_24h = number of distinct actor.login among filtered issues.
  * top_title_repeats = if any exact (case-insensitive, trim) titles appear ≥3 times.
  * hourly_bursts = max count within any rolling 60-minute window among filtered issues (estimate by grouping by hour if needed).
  * concentration =
      - if a single actor authored ≥50% of filtered issues → "actor-concentrated"
      - if ≥30% of issues have highly similar titles (exact match or Jaccard ≥0.8 if available) → "title-concentrated"
- Spike labels (choose one, based on issues_last_24h):
  * ≥ 200 → "massive daily spike"
  * 100–199 → "daily spike"
  * 40–99 → "elevated activity"
  * 0–39 → "normal daily volume"

OUTPUT FORMAT (STRICT):
- Output MUST be a raw JSON array of 3–5 strings (no code fences, no quotes around the array, no escape characters like \\n or \\").
- The array must look exactly like: ["line 1","line 2","line 3"]
- Each line < 25 words.
- Include: event type, actor, repo, number; brief title/purpose; the 24h pattern label; and concrete next steps.

CONTENT GUIDELINES:
- Line 1: Identify event (Issue/PR), number, actor, repo.
- Line 2: Brief title/purpose if available (truncate if long).
- Line 3: Report 24h volume and spike label. Add hourly_bursts if ≥ 5.
- Line 4: Mention concentration or repeats if detected (actor-concentrated or title-concentrated).
- Line 5: Next steps: moderate/lock/triage/rate-limit/CAPTCHA/review.

EXAMPLES (correct raw arrays):

Example 1 (issues daily spike, bursts, concentration):
["Issue #413 opened by @randomuser in backend/api.",
 "Title: 'Login fails after update'.",
 "Daily spike: 140 issues in 24 hours; burst window peak 22.",
 "Actor-concentrated and repeated titles detected.",
 "Enable rate limits, lock new issues, and triage duplicates."]

Example 2 (massive daily spike, repeated titles):
["Issue #901 opened by @bot123 in docs.",
 "Title: 'Free money!!!'.",
 "Massive daily spike: 260 issues in 24 hours.",
 "Title-concentrated spam pattern across reporters.",
 "Close and report accounts, enable CAPTCHA, restrict creation temporarily."]

Example 3 (normal daily volume, no patterns):
["PR #84 opened by @alexdev in frontend.",
 "Implements new user dashboard layout.",
 "Normal daily volume: 18 issues in 24 hours.",
 "No unusual concentration or repeats observed.",
 "Proceed with standard review and triage workflow."]

Final instruction:
Output ONLY the raw JSON array as specified above.
"""


async def generate_activity_spike_summary(payload: dict, issues_last_10m: int):
    response = client.responses.create(
        model="gpt-4o",
        instructions=force_push_instructions,
        input="Event Payload: " + str(payload) + "\nIssues Last 10 Minutes: " + str(issues_last_10m)
    )
    return response.output_text