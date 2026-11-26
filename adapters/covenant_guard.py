from __future__ import annotations
import json
from pathlib import Path
from contracts.schema import CovenantGuardRecord

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "covenant_guard.json"
class CovenantGuardAdapter:
    """Adapter over Covenant Guard / EWS JSON data returning validated Pydantic records."""
    def __init__(self,data_path: Path=DEFAULT_DATA_PATH)->None:
        self.data_path = data_path
        self._records = dict[str,CovenantGuardRecord]()
        self._load()
        
    def _load(self)->None:
        raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        for item in raw.get('records',[]):
            record = CovenantGuardRecord.model_validate(item)
            self._records[record.company_id] = record
            
    def get_by_company(self,company_id: str)->CovenantGuardRecord | None:
        """Get Covenant Guard record for a given company_id."""
        return self._records.get(company_id)
    
    def list_all(self)->list[CovenantGuardRecord]:
        return list(self._records.values())