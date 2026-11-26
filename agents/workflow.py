from __future__ import annotations
import os
from typing import Any
from agent_framework import Agent
from agent_framework.gemini import GeminiChatClient
from agent_framework.openai import OpenAIChatClient, OpenAIChatCompletionClient

try:
    from agent_framework.orchestrations import SequentialBuilder
except ImportError:
    from agent_framework import SequentialBuilder
    
from agents.tools import (
    analyze_supply_chain_contagion,
    get_company_evidence_and_model_audit,
    publish_investigation_report
)

def build_local_llama_client()->OpenAIChatClient:
    """
    Configures OpenAIChatClient against a local Ollama OpenAI-compatible endpoint.
    Set LOCAL_LLM_MODEL (e.g. 'llama3.1' or 'llama3.2') and LOCAL_LLM_BASE_URL in .env.
    """
    base_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
    model = os.getenv("LOCAL_LLM_MODEL", "llama3.1")
    api_key = os.getenv("LOCAL_LLM_API_KEY", "ollama")
    
    return OpenAIChatClient(
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

def build_groq_client() -> OpenAIChatCompletionClient:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("Set GROQ_API_KEY when LLM_PROVIDER=groq.")

    return OpenAIChatCompletionClient(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )

def build_gemini_client() -> GeminiChatClient:
    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("gemini_api_key") or "").strip()
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY (or gemini_api_key) when LLM_PROVIDER=gemini.")

    model = (
        os.getenv("GEMINI_MODEL")
        or os.getenv("gemini_model")
        or "gemini-3.8-flash"
    ).strip()
    return GeminiChatClient(
        model=model,
        api_key=api_key,
    )

def build_chat_client() -> OpenAIChatClient | OpenAIChatCompletionClient | GeminiChatClient:
    provider = os.getenv("LLM_PROVIDER", "local").strip().lower()
    if provider == "local":
        return build_local_llama_client()
    if provider == "groq":
        return build_groq_client()
    if provider == "gemini":
        return build_gemini_client()
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider!r}. Use 'local', 'groq', or 'gemini'.")

def build_contagion_workflow(
    client: OpenAIChatClient | OpenAIChatCompletionClient | GeminiChatClient | None = None,
) -> Any:
    """
    Builds the 4-agent sequential contagion workflow:
    ShockAnalyst -> ExposureInvestigator -> RiskChallenger -> ReportSynthesizer.
    """
    chat_client = client or build_chat_client()
    max_tokens = None
    if isinstance(chat_client, OpenAIChatCompletionClient):
        try:
            max_tokens = int(os.getenv("GROQ_MAX_TOKENS", "512"))
        except ValueError as exc:
            raise ValueError("GROQ_MAX_TOKENS must be a positive integer.") from exc
        if max_tokens < 1:
            raise ValueError("GROQ_MAX_TOKENS must be a positive integer.")
    agent_options = {"max_tokens": max_tokens} if max_tokens is not None else None
    
    shock_analyst = Agent(
        name='shockanalyst',
        client=chat_client,
        default_options=agent_options,
        instructions=(
            "You are the Shock Analyst for ContagionIQ. Extract the commodity or macro shock, "
            "the percentage change (e.g. 20.0), the primary directly hit sector (e.g. 'Steel'), "
            "and downstream sectors ('Auto Components', 'Auto OEMs', 'Infrastructure'). "
            "Respond concisely in 4-6 bullet points."
        ),
    ) 

    exposure_investigator = Agent(
        name='exposureinvestigator',
        client=chat_client,
        default_options=agent_options,
        instructions=(
            "You are the Exposure Investigator. You MUST call `analyze_supply_chain_contagion` "
            "using the shock percentage and primary sector from the Shock Analyst's output before answering. "
            "Never invent company names or financial numbers—report the exact company names, company IDs, "
            "stressed margins, stressed DSCRs, covenant breaches, hop paths, and cited document IDs from the tool output."
        ),
        tools=[analyze_supply_chain_contagion],
    )
    
    risk_challenger = Agent(
        name='riskchallenger',
        client=chat_client,
        default_options=agent_options,
        instructions=(
            "You are the Risk Challenger. Review the Exposure Investigator's findings without "
            "recomputing numbers. Call `get_company_evidence_and_model_audit` for key affected companies "
            "(such as `AUTO_SUP_B` and `INFRA_C`), then ALWAYS write a concise bulleted list of risk flags "
            "(never leave your response empty). Flag low-confidence evidence (<0.82), older filings (e.g. FY2024), "
            "2-hop pass-through attenuation assumptions, and Model Infinity scorecard limitations."
        ),
        tools=[get_company_evidence_and_model_audit]
    )
    
    report_synthesizer = Agent(
        name='reportsynthesizer',
        client=chat_client,
        default_options=agent_options,
        instructions=(
            "You are the Report Synthesizer. Using ONLY the exact company names, company IDs, DSCRs, "
            "covenant thresholds, hop paths, and document IDs from ShockAnalyst, ExposureInvestigator, "
            "and RiskChallenger in the conversation (never invent placeholder companies), write a complete, "
            "detailed Markdown report with these exact five headings:\n"
            "## Shock Assessment\n"
            "## Affected Companies\n"
            "## Exposure Paths & Evidence\n"
            "## Risk Challenger Flags\n"
            "## Recommended Analyst Actions\n\n"
            "In ## Shock Assessment, start with a 2-sentence plain-English takeaway that a non-finance "
            "reader can immediately understand. In ## Affected Companies, include a Markdown table covering "
            "every affected company across Hop 0, "
            "Hop 1, and Hop 2 with Company, Sector, Hop, Base DSCR, Stressed DSCR, Min Covenant, and Status. "
            "Do NOT reply with a short summary sentence—always emit the full 5-section report. "
            "Only call `publish_investigation_report` if the user prompt explicitly asks to publish."
        ),
        tools=[publish_investigation_report],
    )
    return (SequentialBuilder(participants=[
        shock_analyst,exposure_investigator,risk_challenger,report_synthesizer
    ]).build())
    
