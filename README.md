# Canvas Study Planner Agent

A tiny agent + tools that pulls upcoming Canvas assignments and schedules time blocks to work on/study for assignments via the Canvas Calendar. 

This isn't incredibly useful yet but is an example of Canvas AI integration. It's cool that locally runnable models can use tools, such as `Meta-Llama-3.1-8B-Instruct-GGUF` used in this project.

## Setup

1. **Python 3.10+**
2. Install deps:

```bash
pip install requests python-dateutil python-dotenv openai
```

3. Create a `.env` in this folder:

```env
# Canvas
CANVAS_BASE_URL=https://your.canvas.instance
CANVAS_TOKEN=your_canvas_token
TIMEZONE=America/Los_Angeles
DAYS_AHEAD=14

# Language Model (LM Studio / compatible OpenAI-style API)
LM_BASE_URL=http://localhost:1234/v1
LM_API_KEY=lm-studio
LM_MODEL=Meta-Llama-3.1-8B-Instruct-GGUF
```

## Files

* `canvas_tools.py` — Canvas API helpers, **tool implementations** (`get_upcoming_assignments`, `get_submission_status`, `create_canvas_event`), tool **schemas**, and a small **dispatcher**.
* `canvas_agent.py` — Minimal **REPL agent** that imports the tools and follows the docs-compliant tool-call flow.

## Run

```bash
python canvas_agent.py
```

You’ll see the prompt:

```
Assistant: Hi! I can plan study time for your Canvas assignments. (Type 'quit' to exit)
```

## Example workflow

Goal: **Get the next 10 days of assignments and schedule time to complete them using the LM’s estimates.**

### 1) Ask for upcoming work (10 days)

**You:**

```
What assignments are due in the next 10 days?
```

**What happens under the hood:** the agent calls

```
get_upcoming_assignments(days_ahead=10)
```

**Assistant (summarized):**

```
• Course A — Lab 3 — Due: 2025-10-18T23:59:00-07:00
• Course B — Problem Set — Due: 2025-10-19T17:00:00-07:00
...
(ask to adjust window or schedule study time)
```

### 2) Ask to plan & schedule, with estimated durations from the LM

**You:**

```
Please schedule time to do the Course B Problem Set.
```

**What happens:**

1. The LM proposes a plan with estimated durations (e.g., 60–90 mins per session) and concrete time slots in your `TIMEZONE`.
2. To schedule, the agent calls:

```
create_canvas_event(title, start_at, end_at)
```

**Assistant (after tool runs):**

```
I've scheduled a study time event for you from START to END on DATE. You can access the event in your Canvas calendar.
```
## Notes

* Timezone-aware ISO strings are used for events (e.g., `2025-10-12T15:00:00-07:00`).
* `DAYS_AHEAD` defaults to 14 if not set; you can override per request.
* The agent follows a **two-pass** tool-call flow: first pass (with tools) to invoke functions, second pass (no tools) to summarize results.

