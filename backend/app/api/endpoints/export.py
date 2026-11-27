from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.job import ReconJob
from app.models.recon import Entity
from app.services.entity_validation import is_valid_entity_value

router = APIRouter(prefix="/jobs", tags=["Export"])


@router.get("/{job_id}/export/graph")
async def export_job_graph(job_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Exports target domain attack surface as a correlated node-edge topology graph
    with deterministic Phase 4 rule IDs (C001-C005) and supporting evidence.
    """
    job_stmt = select(ReconJob).where(ReconJob.id == job_id)
    job = (await db.execute(job_stmt)).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Recon job not found")

    ent_stmt = select(Entity).where(Entity.job_id == job_id)
    entities = [
        entity for entity in (await db.execute(ent_stmt)).scalars().all()
        if is_valid_entity_value(entity.entity_type, entity.canonical_value)
    ]
    entity_ids = {str(e.id) for e in entities}

    nodes = []
    edges = []
    seen_edges = set()

    for ent in entities:
        attrs = ent.attributes or {}
        nodes.append({
            "id": str(ent.id),
            "label": ent.canonical_value,
            "type": ent.entity_type.value if hasattr(ent.entity_type, "value") else str(ent.entity_type),
            "confidence": float(ent.confidence) if ent.confidence else 0.6,
            "corroborated_by": attrs.get("corroborated_by", []),
            "subnet_cidr": attrs.get("subnet_cidr"),
            "asn": attrs.get("asn"),
            "asn_cidr": attrs.get("asn_cidr"),
            "provider": attrs.get("provider"),
            "asn_country": attrs.get("asn_country"),
            "asn_registry": attrs.get("asn_registry"),
            "asn_records": attrs.get("asn_records", []),
            "asn_source": attrs.get("asn_source"),
            "record_type": attrs.get("record_type"),
            "cname_target": attrs.get("cname_target"),
            "cname_chain": attrs.get("cname_chain", []),
            "service_provider": attrs.get("service_provider"),
            "service_providers": attrs.get("service_providers", []),
            "third_party": attrs.get("third_party"),
            "dangling": attrs.get("dangling")
        })

        # Emit deterministic Phase 4 correlated relationships
        for rel in attrs.get("relationships", []):
            target_id = str(rel.get("target_id", ""))
            if target_id in entity_ids:
                edge_key = (str(ent.id), target_id, rel.get("relationship"), rel.get("rule_id"))
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append({
                        "source": str(ent.id),
                        "target": target_id,
                        "relationship": rel.get("relationship", "RELATED_TO"),
                        "rule_id": rel.get("rule_id", "C001"),
                        "rule_description": rel.get("rule_description", ""),
                        "evidence_sources": rel.get("evidence_sources", [])
                    })

    return JSONResponse(content={
        "target_domain": job.target_domain,
        "job_id": str(job.id),
        "nodes": nodes,
        "edges": edges,
        "graph": {
            "nodes": nodes,
            "edges": edges
        }
    })