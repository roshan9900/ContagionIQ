from __future__ import annotations
from typing import Literal, List
from pathlib import Path
from contracts.schema import ModelInfinityRecord
import json

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "model_infinity.json"

class ModelInfinityAdapter:
    def __init__(self,data_path: Path=DEFAULT_DATA_PATH)->None:
        self.data_path = data_path
        self._models: dict[str,ModelInfinityRecord] = {}
        self._load()
        
    def _load(self)->None:
        raw = json.loads(self.data_path.read_text(encoding='utf-8'))
        for item in raw.get('models',[]):
            record = ModelInfinityRecord.model_validate(item)
            self._models[record.model_id]=record
            
    def get_model(self,model_id:str)->ModelInfinityRecord | None:
        return self._models.get(model_id)
    
    def list_models(self)->list[ModelInfinityRecord]:
        return list(self._models.values())