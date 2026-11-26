from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class CovenantItem(BaseModel):
    covenant_id: str
    metric_type: Literal["DSCR", "LEVERAGE", "ICR"]
    threshold: float
    current_value: float
    status: Literal["COMPLIANT", "WATCH", "BREACH"]
    as_of_date: str
    headroom_pct: float


class EwsSignal(BaseModel):
    signal_id: str
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    description: str
    detected_at: str


class CovenantGuardRecord(BaseModel):
    company_id: str
    company_name: str
    covenants: list[CovenantItem] = Field(default_factory=list)
    ews_signals: list[EwsSignal] = Field(default_factory=list)


class CompanyFinancialsRecords(BaseModel):
    company_id: str
    company_name: str
    sector: str
    revenue_cr: float
    ebitda_cr: float
    debt_cr: float
    cash_cr: float
    interest_expense_cr: float
    annual_debt_service_cr: float
    dso_days: int
    dio_days: int
    dpo_days: int
    covenant_min_dscr: float
    current_dscr: float


class XMineDocumentRecord(BaseModel):
    doc_id: str
    company_id: str
    doc_type: str
    fiscal_year: str
    extracted_text: str
    entities: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class SupplyEdgeRecord(BaseModel):
    source_id: str
    target_id: str
    relationship: Literal["SUPPLIES_TO", "SUBCONTRACTS_TO", "CUSTOMER_OF"]
    dependency_pct: float = Field(ge=0.0, le=1.0)
    evidence_doc_id: str
    evidence_quote: str
    confidence: float = Field(ge=0.0, le=1.0)


class DriftMetrics(BaseModel):
    psi: float
    gini: float
    ks: float


class ModelInfinityRecord(BaseModel):
    model_id: str
    model_type: str
    validation_status: Literal["APPROVED", "CONDITIONAL", "EXPIRED"]
    last_validated: str
    known_limitations: list[str] = Field(default_factory=list)
    drift_metrics: DriftMetrics


class ContagionReport(BaseModel):
    shock_summary: str
    affected_companies: list[str]
    key_breaches: list[str]
    risk_flags: list[str]
    markdown_report: str