from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from agent_framework import AgentResponseUpdate

# Ensure contagioniq root is importable when running `python contagioniq/demo.py` or from inside `contagioniq/`
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.workflow import build_contagion_workflow


DEFAULT_PROMPT = (
    "Coking coal prices increased by 20% due to supply disruption. "
    "Investigate direct and 2-hop downstream contagion across Steel, Auto Components, "
    "Auto OEMs, and Infrastructure."
)


async def run_cli(prompt: str) -> None:
    load_dotenv(ROOT_DIR / ".env")
    workflow = build_contagion_workflow()

    print("=== ContagionIQ CLI Demo (MAF SequentialBuilder) ===")
    print(f"Shock Input: {prompt}\n")

    streamed_text_parts: list[str] = []
    completed_report_text = ""
    async for event in workflow.run(prompt, stream=True):
        data = getattr(event, "data", None)

        if event.executor_id != "reportsynthesizer":
            continue

        if event.type == "output" and isinstance(data, AgentResponseUpdate):
            text = data.text
            if text:
                print(text, end="", flush=True)
                streamed_text_parts.append(text)
        elif event.type == "executor_completed" and isinstance(data, list):
            completed_report_text = "".join(
                update.text for update in data if isinstance(update, AgentResponseUpdate)
            )

    final_text = "".join(streamed_text_parts) or completed_report_text
    if final_text:
        if not streamed_text_parts:
            print(final_text, end="", flush=True)
        print("\n\n=== Final Output ===")
        print(final_text)
    else:
        print("\nNo final report text was emitted by the workflow.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ContagionIQ CLI prototype")
    parser.add_argument(
        "prompt",
        nargs="?",
        default=DEFAULT_PROMPT,
        help="Shock scenario description",
    )
    args = parser.parse_args()
    asyncio.run(run_cli(args.prompt))


if __name__ == "__main__":
    main()