from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from contracts.schema import CompanyFinancialsRecords


DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "i360.json"

class I360Adapter:
    """Adapter over Crisil i360 financial and sector-shock JSON data."""
    def __init__(self,data_path: Path=DEFAULT_DATA_PATH)->None:
        self.data_path = data_path
        self._companies: dict[str,CompanyFinancialsRecords] = {}
        self._sector_shocks: list[dict[str,Any]] = []
        self._load()
        
    def _load(self)->None:
        raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        self._sector_shocks = raw.get("sector_shocks",[])
        for item in raw.get('companies',[]):
            record = CompanyFinancialsRecords.model_validate(item)
            self._companies[record.company_id] = record
            
    def get_company(self,company_id: str)->CompanyFinancialsRecords | None:
        """Get company financials record for a given company_id."""
        return self._companies.get(company_id)
    
    def list_companies(self,sector: str | None=None) -> list[CompanyFinancialsRecords]:
        records = list(self._companies.values())
        if sector:
            target = sector.strip().lower()
            return [r for r in records if r.sector.strip().lower()==target]
        return records
    def list_sector_shocks(self)->list[dict[str,Any]]:
        return list(self._sector_shocks)