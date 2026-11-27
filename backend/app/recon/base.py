from typing import Protocol, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel
from datetime import datetime

class ParsedRecord(BaseModel):
    entity_type: str
    canonical_value: str
    raw_record: Dict[str, Any]

class ModuleRunResult(BaseModel):
    module: str
    status: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    raw_observations: List[ParsedRecord]
    warnings: List[str] = []
    errors: List[str] = []

class PassiveReconModule(Protocol):
    name: str
    version: str

    async def run(self, target: str, job_id: UUID) -> ModuleRunResult:
        ...
