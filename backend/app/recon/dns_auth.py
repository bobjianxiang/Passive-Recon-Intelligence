import asyncio
import hashlib
import time
from datetime import datetime
from uuid import UUID
import dns.asyncresolver
import dns.exception
import dns.resolver
from app.recon.base import ModuleRunResult, ParsedRecord


SERVICE_PROVIDER_SUFFIXES = (
    ("Microsoft 365", (
        "mail.protection.outlook.com",
        "onmicrosoft.com",
        "sharepoint.com",
        "office365.com",
        "outlook.com",
        "microsoftonline.com",
    )),
    ("Azure Front Door", ("azurefd.net",)),
    ("Azure", (
        "azurewebsites.net",
        "trafficmanager.net",
        "cloudapp.azure.com",
        "azure-api.net",
    )),
    ("AWS", (
        "amazonaws.com",
        "cloudfront.net",
        "elasticbeanstalk.com",
        "awsstatic.com",
    )),
    ("Cloudflare", (
        "cloudflare.net",
        "cloudflare.com",
        "pages.dev",
        "workers.dev",
    )),
    ("Unbounce", ("unbouncepages.com", "unbounce.com")),
)

SPECIAL_USE_TLDS = {"example", "invalid", "localhost", "test"}


def _is_special_use_domain(domain: str) -> bool:
    return domain.rstrip(".").lower().rsplit(".", 1)[-1] in SPECIAL_USE_TLDS


def classify_service_provider(hostname: str) -> str | None:
    clean_hostname = hostname.lower().rstrip(".")
    for provider, suffixes in SERVICE_PROVIDER_SUFFIXES:
        if any(
            clean_hostname == suffix or clean_hostname.endswith(f".{suffix}")
            for suffix in suffixes
        ):
            return provider
    return None


def _is_external_to_target(hostname: str, target: str) -> bool:
    return hostname != target and not hostname.endswith(f".{target}")


def _cname_entity_value(hostname: str) -> str:
    value = f"CNAME:{hostname}"
    if len(value) <= 255:
        return value

    digest = hashlib.sha256(hostname.encode("utf-8")).hexdigest()[:12]
    return f"CNAME:{hostname[:236]}:{digest}"


class DnsAuthPassiveModule:
    name: str = "dns_auth"
    version: str = "1.0.0"

    async def _discover_cname_records(
        self,
        resolver: dns.asyncresolver.Resolver,
        target: str,
        hostnames: list[str],
    ) -> tuple[list[ParsedRecord], list[str]]:
        clean_target = target.lower().strip(".")
        candidates = sorted({
            hostname.lower().strip(".")
            for hostname in hostnames
            if hostname
            and (
                hostname.lower().strip(".") == clean_target
                or hostname.lower().strip(".").endswith(f".{clean_target}")
            )
        })
        semaphore = asyncio.Semaphore(10)

        async def inspect_host(hostname: str):
            chain = []
            warnings = []
            current = hostname
            visited = set()
            dangling = False

            async with semaphore:
                for _ in range(8):
                    if current in visited:
                        warnings.append(f"CNAME loop detected while resolving {hostname}")
                        break
                    visited.add(current)

                    try:
                        answers = await resolver.resolve(current, "CNAME")
                    except dns.resolver.NXDOMAIN:
                        dangling = bool(chain)
                        break
                    except dns.resolver.NoAnswer:
                        break
                    except dns.exception.DNSException as exc:
                        warnings.append(f"CNAME lookup for {current} failed: {exc}")
                        break

                    if not answers:
                        break

                    cname_target = str(answers[0].target).lower().rstrip(".")
                    chain.append({"source": current, "target": cname_target})
                    current = cname_target

                if chain and not dangling:
                    try:
                        await resolver.resolve(current, "A")
                    except dns.resolver.NXDOMAIN:
                        dangling = True
                    except dns.resolver.NoAnswer:
                        pass
                    except dns.exception.DNSException as exc:
                        warnings.append(f"CNAME target check for {current} failed: {exc}")

            if not chain:
                return [], warnings

            providers = list(dict.fromkeys(
                provider
                for edge in chain
                if (provider := classify_service_provider(edge["target"]))
            ))
            is_external = any(
                _is_external_to_target(edge["target"], clean_target)
                for edge in chain
            )
            direct_target = chain[0]["target"]
            return [
                ParsedRecord(
                    entity_type="DNS_RECORD",
                    canonical_value=_cname_entity_value(hostname),
                    raw_record={
                        "record_type": "CNAME",
                        "source_host": hostname,
                        "cname_target": direct_target,
                        "cname_chain": chain,
                        "service_provider": providers[0] if providers else None,
                        "service_providers": providers,
                        "third_party": is_external,
                        "dangling": dangling,
                        "source": "dns_auth",
                    },
                )
            ], warnings

        host_results = await asyncio.gather(
            *(inspect_host(hostname) for hostname in candidates)
        )
        records = [record for host_records, _ in host_results for record in host_records]
        warnings = [warning for _, host_warnings in host_results for warning in host_warnings]
        return records, warnings

    async def run(
        self,
        target: str,
        job_id: UUID,
        hostnames: list[str] | None = None,
    ) -> ModuleRunResult:
        started_at = datetime.utcnow()
        start_time = time.time()

        raw_records: list[ParsedRecord] = []
        errors: list[str] = []
        warnings: list[str] = []
        status = "success"

        clean_target = target.strip().lower().strip(".")
        resolver = dns.asyncresolver.Resolver(configure=False)
        resolver.nameservers = ["1.1.1.1", "8.8.8.8", "9.9.9.9"]
        resolver.lifetime = 8.0

        has_spf = False
        has_dmarc = False
        mx_hosts: list[str] = []
        ns_hosts: list[str] = []
        target_nxdomain = False
        target_dns_responded = False
        posture_queries_complete = 0

        try:
            # 1. Query MX Records
            try:
                mx_answers = await resolver.resolve(clean_target, "MX")
                target_dns_responded = True
                posture_queries_complete += 1
                for rdata in mx_answers:
                    mx_host = str(rdata.exchange).rstrip(".").lower()
                    mx_hosts.append(mx_host)
                    provider = classify_service_provider(mx_host)
                    raw_records.append(ParsedRecord(
                        entity_type="DNS_RECORD",
                        canonical_value=f"MX:{mx_host}",
                        raw_record={
                            "record_type": "MX",
                            "preference": int(rdata.preference),
                            "value": mx_host,
                            "service_provider": provider,
                            "third_party": _is_external_to_target(mx_host, clean_target),
                            "source": "dns_auth"
                        }
                    ))
            except dns.resolver.NoAnswer:
                target_dns_responded = True
                posture_queries_complete += 1
            except dns.resolver.NXDOMAIN as e:
                target_nxdomain = True
                posture_queries_complete += 1
                warnings.append(f"MX lookup note: {str(e)}")
            except (dns.exception.DNSException, Exception) as e:
                warnings.append(f"MX lookup note: {str(e)}")

            # 2. Query NS Records
            try:
                ns_answers = await resolver.resolve(clean_target, "NS")
                target_dns_responded = True
                posture_queries_complete += 1
                for rdata in ns_answers:
                    ns_host = str(rdata.target).rstrip(".").lower()
                    ns_hosts.append(ns_host)
                    provider = classify_service_provider(ns_host)
                    raw_records.append(ParsedRecord(
                        entity_type="DNS_RECORD",
                        canonical_value=f"NS:{ns_host}",
                        raw_record={
                            "record_type": "NS",
                            "value": ns_host,
                            "service_provider": provider,
                            "third_party": _is_external_to_target(ns_host, clean_target),
                            "source": "dns_auth"
                        }
                    ))
            except dns.resolver.NoAnswer:
                target_dns_responded = True
                posture_queries_complete += 1
            except dns.resolver.NXDOMAIN as e:
                target_nxdomain = True
                posture_queries_complete += 1
                warnings.append(f"NS lookup note: {str(e)}")
            except (dns.exception.DNSException, Exception) as e:
                warnings.append(f"NS lookup note: {str(e)}")

            # 3. Query TXT Records (detect SPF & security verification tags)
            try:
                txt_answers = await resolver.resolve(clean_target, "TXT")
                target_dns_responded = True
                posture_queries_complete += 1
                for rdata in txt_answers:
                    txt_val = "".join(
                        part.decode("utf-8", errors="ignore") if isinstance(part, bytes) else str(part)
                        for part in rdata.strings
                    )
                    if txt_val.lower().startswith("v=spf1"):
                        has_spf = True
                        raw_records.append(ParsedRecord(
                            entity_type="DNS_RECORD",
                            canonical_value=f"SPF:{txt_val[:180]}",
                            raw_record={
                                "record_type": "SPF",
                                "value": txt_val,
                                "source": "dns_auth"
                            }
                        ))
            except dns.resolver.NoAnswer:
                target_dns_responded = True
                posture_queries_complete += 1
            except dns.resolver.NXDOMAIN as e:
                target_nxdomain = True
                posture_queries_complete += 1
                warnings.append(f"TXT/SPF lookup note: {str(e)}")
            except (dns.exception.DNSException, Exception) as e:
                warnings.append(f"TXT/SPF lookup note: {str(e)}")

            # 4. Query DMARC Record (_dmarc.<target>)
            try:
                dmarc_answers = await resolver.resolve(f"_dmarc.{clean_target}", "TXT")
                posture_queries_complete += 1
                for rdata in dmarc_answers:
                    dmarc_val = "".join(
                        part.decode("utf-8", errors="ignore") if isinstance(part, bytes) else str(part)
                        for part in rdata.strings
                    )
                    if "v=dmarc1" in dmarc_val.lower():
                        has_dmarc = True
                        raw_records.append(ParsedRecord(
                            entity_type="DNS_RECORD",
                            canonical_value=f"DMARC:{dmarc_val[:180]}",
                            raw_record={
                                "record_type": "DMARC",
                                "value": dmarc_val,
                                "source": "dns_auth"
                            }
                        ))
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                posture_queries_complete += 1
            except (dns.exception.DNSException, Exception) as e:
                warnings.append(f"DMARC lookup note: {str(e)}")

            if _is_special_use_domain(clean_target):
                validation_status = "reserved_tld"
                validation_reason = (
                    f".{clean_target.rsplit('.', 1)[-1]} is a special-use suffix, "
                    "not a publicly delegated domain"
                )
            elif target_nxdomain and target_dns_responded:
                validation_status = "inconsistent_dns"
                validation_reason = (
                    "DNS returned both NXDOMAIN and a response for the target; "
                    "target existence is inconclusive"
                )
            elif target_nxdomain:
                validation_status = "nxdomain"
                validation_reason = "DNS returned NXDOMAIN for the target"
            elif target_dns_responded:
                validation_status = "public_dns_responded"
                validation_reason = "DNS responded for the target; ownership is not verified"
            else:
                validation_status = "inconclusive"
                validation_reason = "DNS did not provide a conclusive response for the target"

            raw_records.append(ParsedRecord(
                entity_type="DNS_RECORD",
                canonical_value=f"TARGET_VALIDATION: {validation_status}",
                raw_record={
                    "record_type": "TARGET_VALIDATION",
                    "validation_status": validation_status,
                    "validation_reason": validation_reason,
                    "source": "dns_auth"
                }
            ))

            if (
                validation_status == "public_dns_responded"
                and posture_queries_complete == 4
            ):
                posture_summary = (
                    f"EMAIL_AUTH_POSTURE: SPF={'PRESENT' if has_spf else 'MISSING'}, "
                    f"DMARC={'PRESENT' if has_dmarc else 'MISSING'}, "
                    f"MX_COUNT={len(mx_hosts)}, NS_COUNT={len(ns_hosts)}"
                )
                raw_records.append(ParsedRecord(
                    entity_type="DNS_RECORD",
                    canonical_value=posture_summary,
                    raw_record={
                        "record_type": "EMAIL_AUTH_SUMMARY",
                        "has_spf": has_spf,
                        "has_dmarc": has_dmarc,
                        "mx_hosts": mx_hosts,
                        "ns_hosts": ns_hosts,
                        "source": "dns_auth"
                    }
                ))

            cname_records, cname_warnings = await self._discover_cname_records(
                resolver,
                clean_target,
                hostnames or [clean_target],
            )
            raw_records.extend(cname_records)
            warnings.extend(cname_warnings)

        except Exception as e:
            status = "failed"
            errors.append(str(e))

        finished_at = datetime.utcnow()
        duration_ms = int((time.time() - start_time) * 1000)

        return ModuleRunResult(
            module=self.name,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            raw_observations=raw_records,
            warnings=warnings,
            errors=errors
        )