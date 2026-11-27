from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.recon import Entity, Evidence, EntityType


class ConfidenceEngine:
    """
    Calculates entity confidence scores dynamically based on unique observing sources.
    - Authoritative live DNS/WHOIS records (DNS_RECORD) = 0.95
    - OSINT discoveries (SUBDOMAIN / IP_ADDRESS):
        1 source  = 0.60 (Single tool observation)
        2 sources = 0.80 (Cross-validated by 2 tools)
        3 sources = 0.92 (High confidence validation)
        4+ sources= 1.00 (Maximum confidence validation)
    """

    @staticmethod
    async def recalculate_job_confidence(job_id: UUID, db: AsyncSession):
        stmt = (
            select(Evidence.entity_id, func.count(func.distinct(Evidence.source_module)).label("unique_sources"))
            .where(Evidence.job_id == job_id)
            .group_by(Evidence.entity_id)
        )
        result = await db.execute(stmt)
        evidence_counts = {row.entity_id: row.unique_sources for row in result.all()}

        ent_stmt = select(Entity).where(Entity.job_id == job_id)
        ent_result = await db.execute(ent_stmt)
        entities = ent_result.scalars().all()

        for entity in entities:
            # Live authoritative DNS (SPF/DMARC/MX/NS) and WHOIS records are direct registry lookups
            if entity.entity_type == EntityType.DNS_RECORD:
                entity.confidence = 0.95
                continue

            sources = evidence_counts.get(entity.id, 1)
            if sources == 1:
                score = 0.60
            elif sources == 2:
                score = 0.80
            elif sources == 3:
                score = 0.92
            else:
                score = 1.00

            entity.confidence = score

        await db.commit()