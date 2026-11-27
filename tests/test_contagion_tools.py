import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI

from agents.tools import analyze_supply_chain_contagion, get_company_evidence_and_model_audit
from agents.workflow import build_chat_client, build_contagion_workflow
from agent_framework.gemini import GeminiChatClient
from agent_framework.openai import OpenAIChatCompletionClient


def test_analyze_supply_chain_contagion_returns_exposures_and_model_governance() -> None:
    result = json.loads(analyze_supply_chain_contagion.func(20.0, "Steel", 2))

    assert result["companies"]
    assert result["model_governance"]
    assert any(company["hop"] == 0 for company in result["companies"])

    downstream = [company for company in result["companies"] if company["hop"] > 0]
    assert downstream
    assert all(company["cumulative_pass_through"] > 0 for company in downstream)


def test_analyze_supply_chain_contagion_reaches_hop_2_entities() -> None:
    result = json.loads(analyze_supply_chain_contagion.func(20.0, "Steel", 2))
    hop_2 = [company for company in result["companies"] if company["hop"] == 2]
    hop_2_ids = {company["company_id"] for company in hop_2}

    assert {"OEM_A", "OEM_B", "INFRA_C"} <= hop_2_ids
    oem_a = next(company for company in hop_2 if company["company_id"] == "OEM_A")
    assert oem_a["path"] == "STEEL_A -> AUTO_SUP_A -> OEM_A"
    assert oem_a["cumulative_pass_through"] == pytest.approx(0.189)


def test_analyze_supply_chain_contagion_rejects_negative_inputs() -> None:
    with pytest.raises(ValueError, match="shock_pct must be non-negative"):
        analyze_supply_chain_contagion.func(-5.0, "Steel", 2)

    with pytest.raises(ValueError, match="max_hops must be non-negative"):
        analyze_supply_chain_contagion.func(20.0, "Steel", -1)


def test_company_audit_rejects_unknown_company_id() -> None:
    with pytest.raises(ValueError, match="Unknown company ID"):
        get_company_evidence_and_model_audit.func("UNKNOWN")


def test_groq_workflow_sends_configured_completion_token_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_MAX_TOKENS", "512")
    request_body: dict[str, object] = {}

    def handle_request(request: httpx.Request) -> httpx.Response:
        request_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "qwen/qwen3.8-27b",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Brief response."},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    async def run_agent() -> None:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
        openai_client = AsyncOpenAI(
            api_key="test-key-not-sent",
            base_url="https://api.groq.com/openai/v1",
            http_client=http_client,
        )
        try:
            client = OpenAIChatCompletionClient(
                model="qwen/qwen3.8-27b",
                async_client=openai_client,
            )
            workflow = build_contagion_workflow(client=client)
            await workflow.executors["shockanalyst"].agent.run("Respond briefly.")
        finally:
            await openai_client.close()

    asyncio.run(run_agent())

    assert request_body["max_completion_tokens"] == 512


def test_build_chat_client_supports_gemini_lowercase_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setenv("gemini_api_key", "test-gemini-key")
    monkeypatch.setenv("gemini_model", "gemini-3.1-flash-lite")

    client = build_chat_client()

    assert isinstance(client, GeminiChatClient)
    assert client.model == "gemini-3.1-flash-lite"


def test_build_chat_client_supports_decoupled_llm_config_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "local")
    client = build_chat_client(
        llm_config={
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "api_key": "override-key",
        }
    )
    assert isinstance(client, GeminiChatClient)
    assert client.model == "gemini-3.8-flash"
