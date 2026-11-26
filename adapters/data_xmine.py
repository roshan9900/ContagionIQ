from __future__ import annotations
import json
from pathlib import Path
from contracts.schema import SupplyEdgeRecord, XMineDocumentRecord

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "data_xmine.json"

class DataXMineAdapter:
    def __init__(self,data_path: Path=DEFAULT_DATA_PATH)->None:
        self.data_path = data_path
        self._documents: list[XMineDocumentRecord] = []
        self._edges: list[SupplyEdgeRecord] = []
        self._load()
        
    def _load(self)->None:
        raw = json.loads(self.data_path.read_text(encoding='utf-8'))
        self._documents = [
            XMineDocumentRecord.model_validate(doc) for doc in raw.get('documents',[])
        ]
        self._edges = [
            SupplyEdgeRecord.model_validate(edge) for edge in raw.get('edges',[])
        ]
    
    def list_documents(self,company_id: str | None=None)-> list[XMineDocumentRecord]:
        if company_id:
            return [d for d in self._documents if d.company_id == company_id]
        return list(self._documents)
    
    def list_edges(self)->list[SupplyEdgeRecord]:
        return list(self._edges)