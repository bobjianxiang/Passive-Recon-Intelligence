import re
from uuid import UUID
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from app.models.job import ReconJob
from app.models.recon import Entity, Evidence, EntityType


class CorrelationEngine:
    """
    Phase 4: Deterministic Graph Correlation Engine (Rules C001 - C005).
    Links canonical entities using deterministic rule IDs and supporting evidence provenance.
    """

    RULE_DEFINITIONS = {
        "C001": "Direct DNS A/AAAA Resolution (Subdomain -> IP Address)",
        "C002": "Domain Hierarchy Membership (Root Domain -> Subdomain)",
        "C003": "Shared Infrastructure Co-Hosting (Subdomain <-> Subdomain on Same IP)",
        "C004": "Multi-Source Corroboration (>= 2 Independent OSINT Modules)",
        "C005": "Subnet /24 Netblock Grouping (IP Address -> /24 CIDR Block)"
    }

    @staticmethod
    async def process_job_relationships(job_id: UUID, db: AsyncSession):
        job_stmt = select(ReconJob).where(ReconJob.id == job_id)
        job = (await db.execute(job_stmt)).scalar_one_or_none()
        target_domain = job.target_domain.lower().strip(".") if job else ""

        stmt = select(Evidence).where(Evidence.job_id == job_id)
        evidences = (await db.execute(stmt)).scalars().all()

        ent_stmt = select(Entity).where(Entity.job_id == job_id)
        all_entities = (await db.execute(ent_stmt)).scalars().all()
        entities = {e.canonical_value.lower(): e for e in all_entities}

        # Ensure root DOMAIN entity exists so subdomains always have a parent anchor
        if target_domain and target_domain not in entities:
            root_ent = Entity(
                job_id=job_id,
                entity_type=EntityType.DOMAIN,
                canonical_value=target_domain,
                display_value=target_domain,
                attributes={"relationships": []},
                confidence=1.0
            )
            db.add(root_ent)
            await db.flush()
            entities[target_domain] = root_ent
            all_entities.append(root_ent)

        # Group evidence sources per entity
        entity_sources = defaultdict(set)
        for ev in evidences:
            if ev.entity_id:
                entity_sources[ev.entity_id].add(ev.source_module)

        # Helper to attach deterministic relationship edges without duplicates
        def add_relationship(src_ent: Entity, dst_ent: Entity, rel_type: str, rule_id: str, sources: list[str]):
            if src_ent.id == dst_ent.id:
                return
            attrs = dict(src_ent.attributes or {})
            rels = attrs.get("relationships", [])

            for existing in rels:
                if (
                    existing.get("target_id") == str(dst_ent.id)
                    and existing.get("relationship") == rel_type
                    and existing.get("rule_id") == rule_id
                ):
                    merged = sorted(set(existing.get("evidence_sources", [])) | set(sources))
                    existing["evidence_sources"] = merged
                    attrs["relationships"] = rels
                    src_ent.attributes = attrs
                    flag_modified(src_ent, "attributes")
                    return

            rels.append({
                "target_id": str(dst_ent.id),
                "target_value": dst_ent.canonical_value,
                "relationship": rel_type,
                "rule_id": rule_id,
                "rule_description": CorrelationEngine.RULE_DEFINITIONS[rule_id],
                "evidence_sources": sorted(set(sources))
            })
            attrs["relationships"] = rels

            if rel_type == "RESOLVES_TO":
                resolved_ips = set(attrs.get("resolves_to", []))
                resolved_ips.add(dst_ent.canonical_value)
                attrs["resolves_to"] = sorted(resolved_ips)

            src_ent.attributes = attrs
            flag_modified(src_ent, "attributes")

        ip_regex = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
        ip_to_subdomains = defaultdict(list)

        # --- RULE C001: Direct Subdomain -> IP Resolution across all OSINT tool formats ---
        for ev in evidences:
            raw = ev.raw_record or {}
            src_mod = ev.source_module or "unknown"
            sub_val = None
            ip_val = None

            # Format 1: theHarvester ("sub.domain.com:1.2.3.4")
            if "raw_host" in raw and ":" in str(raw["raw_host"]):
                parts = str(raw["raw_host"]).split(":")
                sub_val = parts[0].lower().strip(".")
                ip_val = parts[1].strip() if len(parts) > 1 else None

            # Format 2: Subfinder JSON ({"host": "sub.domain.com", "ip": "1.2.3.4"})
            elif "host" in raw and "ip" in raw:
                sub_val = str(raw["host"]).lower().strip(".")
                ip_val = str(raw["ip"]).strip()

            # Format 3: Amass discovered_string containing both hostname and IP
            elif "discovered_string" in raw:
                line = str(raw["discovered_string"])
                found_ips = ip_regex.findall(line)
                if found_ips:
                    ip_val = found_ips[0]
                    for token in line.split():
                        clean_tok = token.lower().strip(".,;()[]")
                        if clean_tok in entities and entities[clean_tok].entity_type == EntityType.SUBDOMAIN:
                            sub_val = clean_tok
                            break

            if sub_val in entities and ip_val in entities:
                sub_ent = entities[sub_val]
                ip_ent = entities[ip_val]
                add_relationship(sub_ent, ip_ent, "RESOLVES_TO", "C001", [src_mod])
                ip_to_subdomains[ip_val].append(sub_ent)

        # --- RULE C002: Domain Hierarchy (Root Domain -> Subdomain) ---
        root_entity = entities.get(target_domain)
        if root_entity:
            for ent in all_entities:
                if ent.entity_type == EntityType.SUBDOMAIN and ent.canonical_value.endswith(f".{target_domain}"):
                    sources = list(entity_sources.get(ent.id, {"passive_dns"}))
                    add_relationship(root_entity, ent, "HAS_SUBDOMAIN", "C002", sources)

        # --- RULE C003: Shared Hosting Co-Location (Subdomain <-> Subdomain sharing same IP) ---
        for ip_addr, hosted_subs in ip_to_subdomains.items():
            unique_subs = list({s.id: s for s in hosted_subs}.values())
            if len(unique_subs) > 1:
                for i in range(len(unique_subs)):
                    for j in range(i + 1, len(unique_subs)):
                        add_relationship(
                            unique_subs[i],
                            unique_subs[j],
                            "SHARES_IP_WITH",
                            "C003",
                            [f"shared_ip:{ip_addr}"]
                        )

        # --- RULE C004: Multi-Source Corroboration Metadata ---
        for ent in all_entities:
            sources = sorted(entity_sources.get(ent.id, set()))
            attrs = dict(ent.attributes or {})
            attrs["corroborated_by"] = sources
            if len(sources) >= 2:
                attrs["correlation_rule"] = "C004"
            ent.attributes = attrs
            flag_modified(ent, "attributes")

        # --- RULE C005: Subnet /24 Grouping ---
        subnet_groups = defaultdict(list)
        for ent in all_entities:
            if ent.entity_type == EntityType.IP_ADDRESS and ip_regex.match(ent.canonical_value):
                octets = ent.canonical_value.split(".")
                subnet_cidr = f"{octets[0]}.{octets[1]}.{octets[2]}.0/24"
                subnet_groups[subnet_cidr].append(ent)

        for cidr, ip_ents in subnet_groups.items():
            if len(ip_ents) >= 2:
                for ip_e in ip_ents:
                    attrs = dict(ip_e.attributes or {})
                    attrs["subnet_cidr"] = cidr
                    attrs["subnet_rule"] = "C005"
                    ip_e.attributes = attrs
                    flag_modified(ip_e, "attributes")

        await db.commit()