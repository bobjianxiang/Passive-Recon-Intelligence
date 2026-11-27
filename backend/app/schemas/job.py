from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from uuid import UUID
from datetime import datetime
import re

class JobCreateRequest(BaseModel):
    target_domain: str = Field(..., example="example.com")
    modules: List[str] = Field(default=["amass", "theharvester", "spiderfoot", "reconng"])
    @field_validator("target_domain")
    def validate_and_canonicalise_domain(cls, v: str) -> str:
        domain = v.strip().lower()
        if domain.endswith("."):
            domain = domain[:-1]
        
        # Remove schemes or paths if present
        domain = re.sub(r"^https?://", "", domain)
        domain = domain.split("/")[0]

        # Standard domain regex check
        domain_regex = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
        if not re.match(domain_regex, domain):
            raise ValueError("Invalid root domain format.")
        return domain

class JobResponse(BaseModel):
    id: UUID
    target_domain: str
    status: str
    selected_modules: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True
