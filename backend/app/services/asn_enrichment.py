import asyncio
import ipaddress
from uuid import UUID

import dns.asyncresolver
import dns.exception
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recon import Entity, EntityType
from app.services.entity_validation import normalize_ip_address


def build_cymru_query_name(ip_value: str) -> str:
    address = ipaddress.ip_address(ip_value)
    if isinstance(address, ipaddress.IPv4Address):
        reverse_address = ".".join(reversed(str(address).split(".")))
        return f"{reverse_address}.origin.asn.cymru.com"

    reverse_nibbles = ".".join(reversed(address.exploded.replace(":", "")))
    return f"{reverse_nibbles}.origin6.asn.cymru.com"


def parse_cymru_record(value: str) -> dict[str, str] | None:
    fields = [field.strip() for field in value.split("|")]
    if len(fields) < 6:
        return None

    asn_number = fields[0].upper().removeprefix("AS")
    if not asn_number.isdigit():
        return None

    try:
        prefix = ipaddress.ip_network(fields[1], strict=False)
    except ValueError:
        return None

    return {
        "asn": f"AS{asn_number}",
        "asn_cidr": str(prefix),
        "provider": fields[5],
        "asn_country": fields[2],
        "asn_registry": fields[3],
    }


class ASNEnrichmentService:
    @staticmethod
    async def enrich_job_ips(job_id: UUID, db: AsyncSession) -> list[str]:
        result = await db.execute(
            select(Entity).where(
                Entity.job_id == job_id,
                Entity.entity_type == EntityType.IP_ADDRESS,
            )
        )
        entities = result.scalars().all()
        if not entities:
            return []

        resolver = dns.asyncresolver.Resolver(configure=False)
        resolver.nameservers = ["1.1.1.1", "8.8.8.8", "9.9.9.9"]
        resolver.lifetime = 6.0
        semaphore = asyncio.Semaphore(10)

        async def lookup(entity):
            ip_value = normalize_ip_address(entity.canonical_value)
            if not ip_value:
                return entity, [], None

            address = ipaddress.ip_address(ip_value)
            if not address.is_global:
                return entity, [], f"ASN lookup skipped for non-public IP {ip_value}"

            query_name = build_cymru_query_name(ip_value)
            async with semaphore:
                try:
                    answer = await resolver.resolve(query_name, "TXT")
                except dns.exception.DNSException as exc:
                    return entity, [], f"Cymru lookup for {ip_value} failed: {exc}"

            records = []
            for rdata in answer:
                txt_value = b"".join(rdata.strings).decode("utf-8", errors="replace")
                parsed = parse_cymru_record(txt_value)
                if parsed:
                    records.append(parsed)

            unique_records = {
                (record["asn"], record["asn_cidr"]): record for record in records
            }
            records = [
                unique_records[key] for key in sorted(unique_records)
            ]
            if not records:
                return entity, [], f"No Cymru origin record returned for {ip_value}"
            return entity, records, None

        results = await asyncio.gather(*(lookup(entity) for entity in entities))
        warnings = []
        for entity, records, warning in results:
            if warning:
                warnings.append(warning)
            if not records:
                continue

            attributes = dict(entity.attributes or {})
            attributes.update(records[0])
            attributes["asn_records"] = records
            attributes["asn_source"] = "Team Cymru DNS"
            entity.attributes = attributes

        return warnings
