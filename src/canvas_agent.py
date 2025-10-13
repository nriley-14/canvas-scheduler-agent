"""
Agent / REPL that imports tools from canvas_tools.py
"""

from __future__ import annotations

import json
import os
from typing import List, Dict, Any

from dotenv import load_dotenv
from openai import OpenAI

from canvas_tools import TOOLS, execute_function

load_dotenv()

LM_BASE_URL = os.getenv("LM_BASE_URL")
LM_API_KEY = os.getenv("LM_API_KEY")
LM_MODEL = os.getenv("LM_MODEL")

TZ = os.getenv("TIMEZONE", "America/Los_Angeles")
DAYS_AHEAD_DEFAULT = int(os.getenv("DAYS_AHEAD_DEFAULT"))

if not (LM_BASE_URL and LM_API_KEY and LM_MODEL):
    raise RuntimeError("LM_BASE_URL, LM_API_KEY, and LM_MODEL must be set in env")

client = OpenAI(base_url=LM_BASE_URL, api_key=LM_API_KEY)


def run_turn(messages: List[Dict[str, Any]]):
    """Docs-compliant tool-use flow."""
    # First call with tools
    resp = client.chat.completions.create(
        model=LM_MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.0,
    )

    msg = resp.choices[0].message

    if getattr(msg, "tool_calls", None):
        messages.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        # Execute tools
        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            result = execute_function(name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        # Second call without tools
        final = client.chat.completions.create(
            model=LM_MODEL, messages=messages, temperature=0.0
        )
        final_msg = final.choices[0].message.content or ""
        messages.append({"role": "assistant", "content": final_msg})
        return final_msg, messages

    # No tools requested respond normally
    content = msg.content or ""
    messages.append({"role": "assistant", "content": content})
    return content, messages


def main():
    system_prompt = f"""
    You can call tools to help plan study time for Canvas assignments.

    TOOLS YOU CAN CALL:
    - get_upcoming_assignments(days_ahead)
    - get_submission_status(course_id, assignment_id)
    - create_canvas_event(title, start_at, end_at)

    Instructions:
    1) When asked about upcoming assignments, call get_upcoming_assignments with a sensible window (default {DAYS_AHEAD_DEFAULT} days).
    2) After a tool result (JSON), summarize clearly:
    - If there are assignments: list each as "Course — Assignment — Due (ISO)".
    - If none: say there are none in that window.
    3) Offer to adjust the window (e.g., 1, 7, or 21 days).
    4) If the user asks to schedule study time, propose events and then call create_canvas_event.
    5) Use timezone {TZ} when proposing ISO timestamps.

    Be concise.
    """

    conversation: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    print(
        "Assistant: Hi! I can plan study time for your Canvas assignments. (Type 'quit' to exit)"
    )
    while True:
        try:
            user = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not user:
            continue
        if user.lower() in {"quit", "exit"}:
            print("Bye!")
            break

        conversation.append({"role": "user", "content": user})
        reply, convo = run_turn(conversation)
        print(f"Assistant: {reply}")


if __name__ == "__main__":
    main()
