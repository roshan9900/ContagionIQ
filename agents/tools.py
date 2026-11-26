from __future__ import annotations
import json
from typing import Annotated, Any
from agent_framework import tool
from pydantic import Field
from adapters.covenant_guard import CovenantGuardAdapter
from adapters.data_xmine import DataXMineAdapter
from adapters.i360 import I360Adapter
from adapters.model_infinity import ModelInfinityAdapter
from engine.financials import FinancialStressEngine
from engine.graph import SupplyChainGraphEngine

_i360_adapter = I360Adapter()
_covenant_adapter = CovenantGuardAdapter()
_xmin_adapter = DataXMineAdapter()
_model_adapter = ModelInfinityAdapter()

_graph_engine = SupplyChainGraphEngine(_xmin_adapter.list_edges())
_financial_engine = FinancialStressEngine(raw_material_share_of_cogs=0.55)


@tool
def analyze_supply_chain_contagion(
    shock_pct: Annotated[
        float,
        Field(description="Magnitude of commodity cost shock in percent, e.g., 20.0 for +20%"),
    ],
    primary_sector: Annotated[
        str,
        Field(description="Directly shocked upstream sector, e.g., 'Steel'"),
    ]="Steel",
    max_hops: Annotated[
        int,
        Field(description="Maximum downstream contagion hop depth, e.g., 2")
    ]=2,
)->str:
    """
    Traces multi-hop supply-chain contagion from companies in primary_sector and runs
    deterministic financial stress calculations (EBITDA margin, DSCR, covenant breaches,
    working-capital drag, and evidence trail) across direct and downstream entities.
    """
    if shock_pct < 0:
        raise ValueError("shock_pct must be non-negative")
    if max_hops < 0:
        raise ValueError("max_hops must be non-negative")

    seed_companies = _i360_adapter.list_companies(sector=primary_sector)
    seed_id = [c.company_id for c in seed_companies]
    model_governance = [model.model_dump() for model in _model_adapter.list_models()]
    results: list[dict[str, Any]] = []
    
    for company in seed_companies:
        cov = _covenant_adapter.get_by_company(company.company_id)
        metrics = _financial_engine.stress_company(
            company=company,
            shock_pct=shock_pct,
            pass_through_factor=1.0,
            is_direct_shock=True,
            covenant_record=cov,
        )
        results.append(
            {
                'hop':0,
                'path':company.company_id,
                'relationship':'DIRECT_SHOCK',
                'direct_dependency_pct':100.0,
                'cumulative_pass_through':1.0,
                'evidence':[
                    {
                    'from':'SHOCK_EVENT',
                    'to':company.company_id,
                    'doc_id':'i360-SHOCK_FEED',
                    'confidence':1.0,
                    'quote':f"Direct {shock_pct:.1f}% input cost shock in {company.sector}",
                    }
                ],
                **metrics
            }
        )
    downstream_paths = _graph_engine.traverse_exposure(seed_company_ids=seed_id,max_hops=max_hops)
    for item in downstream_paths:
        target_id = item['company_id']
        company = _i360_adapter.get_company(target_id)
        if company is None:
            continue
        cov = _covenant_adapter.get_by_company(target_id)
        metrics = _financial_engine.stress_company(
            company=company,
            shock_pct=shock_pct,
            pass_through_factor=item['cumulative_pass_through'],
            is_direct_shock=False,
            covenant_record=cov,
        )
        results.append(
            {
                **item,
                **metrics
            }
        )
    return json.dumps(
        {
            "companies": results,
            "model_governance": model_governance,
        },
        separators=(",", ":"),
    )

@tool
def get_company_evidence_and_model_audit(
    company_id:Annotated[
        str,
        Field(description="Company identifier such as 'AUTO_SUP_B' or 'INFRA_A'"),
    ],
)->str:
    """
    Retrieves Data XMine extracted filings and Model Infinity validation metadata
    for a specific company so risk challenges can cite concrete documents and model caveats.
    """
    company = _i360_adapter.get_company(company_id=company_id)
    if company is None:
        raise ValueError(f"Unknown company ID: {company_id}")

    docs = [d.model_dump() for d in _xmin_adapter.list_documents(company_id)]
    return json.dumps(
        {
            'company_id':company_id,
            'company_name':company.company_name,
            'documents':docs,
            'model_governance':[
                model.model_dump() for model in _model_adapter.list_models()
            ],
        },
        separators=(",", ":"),
    )  
    
@tool(approval_mode="always_require")
def publish_investigation_report(
    report_title: Annotated[
        str,
        Field(description="Title of the finalized contagion investigation report"),
    ],
    executive_summary: Annotated[
        str,
        Field(description="Concise summary of affected companies, breaches, and key flags"),
    ],
) ->str:
    """
    Publishes the finalized contagion report to the EI analyst review queue.
    Always requires explicit human-in-the-loop approval before execution.
    """
    return json.dumps(
        {
            'status':'PUBLISHED',
            'report_title':report_title,
            'executive_summary':executive_summary,
        }
    )