from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.job import ReconJob
from app.models.recon import Entity, EntityType
from app.services.llm import LLMBriefingEngine
from app.services.briefing_cache import get_cached_briefing
from app.services.entity_validation import is_valid_entity_value

router = APIRouter(prefix="/jobs", tags=["LLM Analysis"])


@router.get("/{job_id}/summary")
async def generate_job_security_briefing(
    job_id: UUID,
    generate_if_missing: bool = True,
    db: AsyncSession = Depends(get_db),
):
    job_stmt = select(ReconJob).where(ReconJob.id == job_id)
    job = (await db.execute(job_stmt)).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Recon job not found")

    ent_stmt = select(Entity).where(Entity.job_id == job_id)
    entities = [
        entity for entity in (await db.execute(ent_stmt)).scalars().all()
        if is_valid_entity_value(entity.entity_type, entity.canonical_value)
        and not (
            entity.entity_type == EntityType.SUBDOMAIN
            and entity.canonical_value.lower().rstrip(".")
            == job.target_domain.lower().rstrip(".")
        )
    ]

    if not entities:
        return {
            "job_id": str(job_id),
            "target_domain": job.target_domain,
            "metrics": {"total_subdomains": 0, "total_ips": 0, "high_confidence_count": 0, "low_confidence_count": 0},
            "entities": [],
            "briefing_status": "no_entities",
            "briefing_markdown": "No entities discovered for this job run."
        }

    subdomains = [e for e in entities if e.entity_type == EntityType.SUBDOMAIN]
    ips = [e for e in entities if e.entity_type == EntityType.IP_ADDRESS]
    assets = subdomains + ips
    high_conf = [e for e in assets if float(e.confidence or 0.0) >= 0.80]
    low_conf = [e for e in assets if float(e.confidence or 0.0) < 0.80]

    metrics = {
        "total_subdomains": len(subdomains),
        "total_ips": len(ips),
        "high_confidence_count": len(high_conf),
        "low_confidence_count": len(low_conf)
    }

    # Serialize entities for frontend charts & table
    serialized_entities = []
    for ent in entities:
        attributes = ent.attributes or {}
        serialized_entities.append({
            "id": str(ent.id),
            "value": ent.canonical_value,
            "type": ent.entity_type.value if hasattr(ent.entity_type, 'value') else str(ent.entity_type),
            "confidence": float(ent.confidence) if ent.confidence else 0.6,
            "resolves_to": attributes.get("resolves_to", []),
            "relationships": attributes.get("relationships", []),
            "corroborated_by": attributes.get("corroborated_by", []),
            "subnet_cidr": attributes.get("subnet_cidr"),
            "asn": attributes.get("asn"),
            "asn_cidr": attributes.get("asn_cidr"),
            "provider": attributes.get("provider"),
            "asn_country": attributes.get("asn_country"),
            "asn_registry": attributes.get("asn_registry"),
            "asn_records": attributes.get("asn_records", []),
            "asn_source": attributes.get("asn_source"),
            "record_type": attributes.get("record_type"),
            "validation_status": attributes.get("validation_status"),
            "validation_reason": attributes.get("validation_reason"),
            "cname_target": attributes.get("cname_target"),
            "cname_chain": attributes.get("cname_chain", []),
            "service_provider": attributes.get("service_provider"),
            "service_providers": attributes.get("service_providers", []),
            "third_party": attributes.get("third_party"),
            "dangling": attributes.get("dangling")
        })

    # Sort highest confidence first
    serialized_entities.sort(key=lambda x: x["confidence"], reverse=True)

    # CACHE HIT
    cached_briefing = get_cached_briefing(job.briefing_markdown)
    if cached_briefing is not None:
        return {
            "job_id": str(job.id),
            "target_domain": job.target_domain,
            "metrics": metrics,
            "entities": serialized_entities,
            "briefing_status": "cached",
            "briefing_markdown": cached_briefing
        }

    if not generate_if_missing:
        return {
            "job_id": str(job.id),
            "target_domain": job.target_domain,
            "metrics": metrics,
            "entities": serialized_entities,
            "briefing_status": "missing",
            "briefing_markdown": (
                "No saved AI briefing is available for this job. "
                "Stored reconnaissance findings are shown below."
            )
        }

    # CACHE MISS
    briefing_engine = LLMBriefingEngine()
    briefing_md = await briefing_engine.generate_briefing(job.target_domain, metrics, serialized_entities[:30])

    job.briefing_markdown = briefing_md
    await db.commit()

    return {
        "job_id": str(job.id),
        "target_domain": job.target_domain,
        "metrics": metrics,
        "entities": serialized_entities,
        "briefing_status": "generated",
        "briefing_markdown": briefing_md
    }