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

Given a PushEvent payload, analyze it and summarize the incident as a concise list.

Formatting rules:
- Output must be a *raw JSON array*, not a string.
- Do NOT wrap the array in quotes or code fences.
- Do NOT include escape characters like \\n or \\\".
- The output must look exactly like this:
  ["line 1", "line 2", "line 3"]
- Array length: 3–5 items.
- Each item under 25 words.
- Combine root cause, impact, and next steps into one unified list.
- Include branch name, actor, and commit SHAs if available.
- Do not include markdown, explanations, or section headers.

Examples:

Example 1:
["Force-push on master rewrote commits (27dcd146 → 6d7fce94) by @jboning.",
 "Repo history diverged; prior commits may be lost.",
 "Developers may face non-fast-forward pull errors.",
 "Verify commit range and restore missing work.",
 "Enable branch protection to block future force-pushes."]

Example 2:
["Force-push detected on main by @devsmith (a12b3c → e98f7d).",
 "History rewrite may cause broken references.",
 "Rebase or squash likely triggered overwrite.",
 "Notify team and reset local branches.",
 "Harden branch protection policies."]

Now analyze the given PushEvent payload and output ONLY the raw JSON array as specified above.
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

Inputs:
- event_payload: JSON payload of either an IssuesEvent (action = "opened") or PullRequestEvent (action = "opened").
- issues_last_10m: integer count of issues opened in the last 10 minutes.

Output format (STRICT):
- Output must be a raw JSON array of 3–5 strings.
- Do NOT wrap the array in quotes or code fences.
- Do NOT include escape characters like \\n or \\\".
- Do NOT include keys, labels, or extra prose.
- The output must look exactly like: ["line 1","line 2","line 3"]

Content rules:
- Identify event type: "Issue opened" or "Pull Request opened".
- Mention actor, repository, and number (issue/PR).
- Briefly summarize the title/purpose if available.
- Emphasize spam detection using issues_last_10m:
  - >= 20 → "massive spam spike"
  - 10–19 → "spam spike"
  - 3–9 → "suspicious uptick"
  - 0–2 → "normal activity"
- Include concrete next steps (moderate, lock, triage, rate-limit, review).

Examples (correct raw arrays):

Example 1 (spam spike in issues):
["Issue #413 opened by @randomuser in backend/api.",
 "Title: 'Login fails after update'.",
 "Spam spike: 14 issues in 10 minutes.",
 "Lock issue creation; review accounts.",
 "Enable rate limits or CAPTCHA."]

Example 2 (massive PR spam):
["PR #217 opened by @bot123 in docs.",
 "Empty or irrelevant content detected.",
 "Massive spam spike: 25 items in 10 minutes.",
 "Close and report spam accounts immediately.",
 "Restrict contributors temporarily."]

Example 3 (normal PR):
["PR #84 opened by @alexdev in frontend.",
 "Implements new user dashboard layout.",
 "Normal activity: 1 issue in 10 minutes.",
 "Proceed with standard code review workflow."]

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