import asyncio
from uuid import UUID
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.job import ReconJob, JobStatus
from app.models.recon import ModuleRun, RawObservation, Entity, Evidence, EntityType
from app.recon.amass import AmassPassiveModule
from app.recon.theharvester import TheHarvesterPassiveModule
from app.recon.subfinder import SubfinderPassiveModule
from app.recon.waybackurls import WaybackurlsPassiveModule
from app.recon.dns_auth import DnsAuthPassiveModule
from app.recon.whois_lookup import WhoisPassiveModule
from app.services.correlation import CorrelationEngine
from app.services.confidence import ConfidenceEngine
from app.services.asn_enrichment import ASNEnrichmentService


async def execute_recon_pipeline(job_id: UUID):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ReconJob).where(ReconJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return

        job.status = JobStatus.COLLECTING
        await db.commit()

        try:
            amass_module = AmassPassiveModule()
            harvester_module = TheHarvesterPassiveModule()
            subfinder_module = SubfinderPassiveModule()
            wayback_module = WaybackurlsPassiveModule()
            dns_auth_module = DnsAuthPassiveModule()
            whois_module = WhoisPassiveModule()

            # Collect hosts first so DNS Auth can inspect their CNAME dependencies.
            mod_results = await asyncio.gather(
                amass_module.run(job.target_domain, job.id),
                harvester_module.run(job.target_domain, job.id),
                subfinder_module.run(job.target_domain, job.id),
                wayback_module.run(job.target_domain, job.id),
                whois_module.run(job.target_domain, job.id),
                return_exceptions=True
            )

            discovered_hosts = {job.target_domain}
            for result in mod_results:
                if isinstance(result, Exception):
                    continue
                discovered_hosts.update(
                    observation.canonical_value
                    for observation in result.raw_observations
                    if observation.entity_type in {"DOMAIN", "SUBDOMAIN"}
                )

            dns_auth_results = await asyncio.gather(
                dns_auth_module.run(
                    job.target_domain,
                    job.id,
                    hostnames=sorted(discovered_hosts),
                ),
                return_exceptions=True,
            )
            mod_results.extend(dns_auth_results)

            successful_runs = 0
            module_runs_by_name = {}

            for res in mod_results:
                if isinstance(res, Exception):
                    continue

                module_run = ModuleRun(
                    job_id=job.id,
                    module_name=res.module,
                    status=res.status,
                    started_at=res.started_at,
                    finished_at=res.finished_at,
                    duration_ms=res.duration_ms,
                    warnings={"warnings": res.warnings} if res.warnings else None,
                    errors={"errors": res.errors} if res.errors else None
                )
                db.add(module_run)
                await db.flush()
                module_runs_by_name[res.module] = module_run

                if res.status in ["success", "partial_success"]:
                    successful_runs += 1

                for obs in res.raw_observations:
                    raw_obs = RawObservation(
                        job_id=job.id,
                        module_run_id=module_run.id,
                        observation_type=obs.entity_type,
                        raw_value=obs.canonical_value,
                        raw_record=obs.raw_record
                    )
                    db.add(raw_obs)

                    try:
                        target_entity_type = EntityType[obs.entity_type]
                    except KeyError:
                        target_entity_type = EntityType.SUBDOMAIN

                    stmt = select(Entity).where(
                        Entity.job_id == job.id,
                        Entity.entity_type == target_entity_type,
                        Entity.canonical_value == obs.canonical_value
                    )
                    existing_entity = (await db.execute(stmt)).scalar_one_or_none()

                    if not existing_entity:
                        initial_conf = 0.95 if target_entity_type == EntityType.DNS_RECORD else 0.60
                        existing_entity = Entity(
                            job_id=job.id,
                            entity_type=target_entity_type,
                            canonical_value=obs.canonical_value,
                            display_value=obs.canonical_value,
                            confidence=initial_conf
                        )
                        db.add(existing_entity)
                        await db.flush()

                    if obs.entity_type == "DNS_RECORD":
                        record_type = obs.raw_record.get("record_type")
                        if record_type == "CNAME":
                            record_attributes = {
                                "record_type": "CNAME",
                                "cname_target": obs.raw_record.get("cname_target"),
                                "cname_chain": obs.raw_record.get("cname_chain", []),
                                "service_provider": obs.raw_record.get("service_provider"),
                                "service_providers": obs.raw_record.get("service_providers", []),
                                "third_party": obs.raw_record.get("third_party", False),
                                "dangling": obs.raw_record.get("dangling", False),
                            }
                        elif record_type in {"MX", "NS"}:
                            provider = obs.raw_record.get("service_provider")
                            record_attributes = {
                                "record_type": record_type,
                                "service_provider": provider,
                                "service_providers": [provider] if provider else [],
                                "third_party": obs.raw_record.get("third_party", False),
                            }
                        else:
                            record_attributes = {}

                        if record_attributes:
                            existing_entity.attributes = {
                                **(existing_entity.attributes or {}),
                                **record_attributes,
                            }

                    evidence = Evidence(
                        job_id=job.id,
                        entity_id=existing_entity.id,
                        module_run_id=module_run.id,
                        source_module=res.module,
                        source_type="passive_recon",
                        observed_value=obs.canonical_value,
                        raw_record=obs.raw_record
                    )
                    db.add(evidence)

            asn_warnings = await ASNEnrichmentService.enrich_job_ips(job.id, db)
            dns_auth_run = module_runs_by_name.get("dns_auth")
            if asn_warnings and dns_auth_run:
                warning_data = dict(dns_auth_run.warnings or {})
                warning_data["asn_enrichment"] = asn_warnings
                dns_auth_run.warnings = warning_data

            # 1. Execute Relationship Correlation Engine (C001-C005)
            await CorrelationEngine.process_job_relationships(job.id, db)

            # 2. Recalculate Dynamic Evidence Confidence Scores across collectors
            await ConfidenceEngine.recalculate_job_confidence(job.id, db)

            if successful_runs == len(mod_results):
                job.status = JobStatus.COMPLETED
            elif successful_runs > 0:
                job.status = JobStatus.PARTIAL_SUCCESS
            else:
                job.status = JobStatus.FAILED

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_summary = {"error": str(e)}

        await db.commit()