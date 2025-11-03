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
- Output must be a valid JSON array of 3–5 short strings.
- Each string should be under 25 words.
- Combine root cause, impact, and next steps into one unified list.
- Focus on who performed the force-push, what changed, and what to do next.
- Include branch name, actor, and commit SHAs if present.
- Do not include headers, explanations, or markdown.

Examples:

Example 1:
[
  "Force-push on master rewrote commits (27dcd146 → 6d7fce94) by @jboning.",
  "Repo history diverged; prior commits may be lost.",
  "Developers may face non-fast-forward pull errors.",
  "Verify commit range and restore missing work.",
  "Enable branch protection to block future force-pushes."
]

Example 2:
[
  "Force-push detected on main by @devsmith (a12b3c → e98f7d).",
  "History rewrite may cause broken references.",
  "Rebase or squash likely triggered overwrite.",
  "Notify team and reset local branches.",
  "Harden branch protection policies."
]

Now analyze the given PushEvent payload and produce a 3–5 bullet JSON array summary describing the force-push incident.
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

Inputs you will receive:
- event_payload: JSON payload of either an IssuesEvent (action = "opened") or PullRequestEvent (action = "opened").
- issues_last_10m: integer count of issues opened in the last 10 minutes.

Your goal:
- Generate a short unified summary (3–5 bullet points total).
- Combine root cause, impact, and next steps in one list.
- Output ONLY a valid JSON array of concise strings (no markdown, no explanations).
- Each string must be under 25 words.

Content rules:
- Identify event type: “Issue opened” or “Pull Request opened”.
- Mention actor, repo, and number (issue or PR).
- Summarize purpose briefly using the title if available.
- Emphasize **spam detection**:
  - If issues_last_10m >= 20 → treat as “massive spam spike”.
  - If 10 ≤ issues_last_10m < 20 → treat as “spam spike”.
  - If 3 ≤ issues_last_10m < 10 → treat as “suspicious uptick”.
  - Otherwise → normal activity.
- Next steps should include moderation or investigation actions when spam is suspected.

Examples:

Example 1 (spam spike in issues):
[
  "Issue #413 opened by @randomuser in repo/backend.",
  "Title: 'Fix urgent login bug'.",
  "Spike: 14 issues in 10 minutes; likely spam burst.",
  "Temporarily lock issue creation and review accounts.",
  "Enable rate limits or CAPTCHA verification."
]

Example 2 (massive PR spam):
[
  "PR #217 opened by @bot123 in repo/docs.",
  "Empty or irrelevant content detected.",
  "Massive spam spike: 25 new items in 10 minutes.",
  "Close and report spam accounts immediately.",
  "Enable contributor restrictions on repository."
]

Example 3 (normal PR):
[
  "PR #84 opened by @alexdev in repo/frontend.",
  "Implements new user dashboard layout.",
  "No spam activity detected (1 issue in 10 minutes).",
  "Proceed with standard code review workflow."
]

Output format reminder:
- Always a JSON array of 3–5 strings.
- Each string under 25 words.
- Never include markdown, extra text, or commentary.

Now, analyze the given event_payload and issues_last_10m, and output the summary as described above.
"""


async def generate_activity_spike_summary(payload: dict, issues_last_10m: int):
    response = client.responses.create(
        model="gpt-4o",
        instructions=force_push_instructions,
        input="Event Payload: " + str(payload) + "\nIssues Last 10 Minutes: " + str(issues_last_10m)
    )
    return response.output_text