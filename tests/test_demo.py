import asyncio
from types import SimpleNamespace

from agent_framework import AgentResponseUpdate, Content

import demo


def test_cli_renders_text_updates_and_ignores_executor_bookkeeping(monkeypatch, capsys) -> None:
    class FakeWorkflow:
        def run(self, prompt: str, *, stream: bool = False):
            assert prompt == "test prompt"
            assert stream

            async def events():
                yield SimpleNamespace(
                    type="executor_completed",
                    executor_id="exposureinvestigator",
                    data=[
                        AgentResponseUpdate(
                            contents=[Content.from_text(text="not user-facing")]
                        )
                    ],
                )
                yield SimpleNamespace(
                    type="output",
                    executor_id="reportsynthesizer",
                    data=AgentResponseUpdate(
                        contents=[Content.from_text(text="Report ")]
                    ),
                )
                yield SimpleNamespace(
                    type="output",
                    executor_id="reportsynthesizer",
                    data=AgentResponseUpdate(
                        contents=[Content.from_text(text="text")]
                    ),
                )

            return events()

    monkeypatch.setattr(demo, "build_contagion_workflow", FakeWorkflow)

    asyncio.run(demo.run_cli("test prompt"))

    output = capsys.readouterr().out
    assert "Report text" in output
    assert "not user-facing" not in output
    assert "AgentResponseUpdate object" not in output


def test_cli_uses_final_executor_updates_when_no_output_events_are_emitted(
    monkeypatch, capsys
) -> None:
    class FakeWorkflow:
        def run(self, prompt: str, *, stream: bool = False):
            async def events():
                yield SimpleNamespace(
                    type="executor_completed",
                    executor_id="reportsynthesizer",
                    data=[
                        AgentResponseUpdate(
                            contents=[Content.from_text(text="Final report")]
                        )
                    ],
                )

            return events()

    monkeypatch.setattr(demo, "build_contagion_workflow", FakeWorkflow)

    asyncio.run(demo.run_cli("test prompt"))

    output = capsys.readouterr().out
    assert "Final report" in output
    assert "AgentResponseUpdate object" not in output
