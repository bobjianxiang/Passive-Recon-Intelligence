import ipaddress
import os
import re
from typing import Dict, Any, List, Set
from ollama import AsyncClient


class LLMBriefingEngine:
    """
    Phase 6 & Phase 7: Grounds passive recon graph findings, DNS/Email Auth (SPF/DMARC/MX),
    WHOIS registrar records, and Phase 4 correlation relationships (C001-C005) into strict
    context, queries a local Ollama LLM, and enforces a deterministic post-generation Grounding
    Gate that rejects/flags any hallucinated or fabricated entity references.
    """

    def __init__(self):
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
        self.model_name = os.getenv("LLM_MODEL", "qwen2.5:latest")

    def _build_grounding_prompt(
        self,
        target_domain: str,
        metrics: Dict[str, Any],
        top_entities: List[Dict[str, Any]],
    ) -> str:
        formatted_assets = []
        formatted_dns_whois = []

        for e in top_entities:
            ent_id = e.get("id", "unknown")
            val = e.get("value", "")
            e_type = e.get("type", "SUBDOMAIN")
            conf = e.get("confidence", 0.6)
            resolves = e.get("resolves_to", [])
            corroborated_by = e.get("corroborated_by", [])
            subnet_cidr = e.get("subnet_cidr")
            relationships = e.get("relationships", [])

            if e_type == "DNS_RECORD":
                record_type = e.get("record_type")
                line = f"- [{ent_id}] {val}"
                providers = e.get("service_providers") or []
                if not providers and e.get("service_provider"):
                    providers = [e["service_provider"]]
                if providers:
                    line += f" | service provider: {', '.join(providers)}"
                if e.get("third_party"):
                    line += " | external service"
                if record_type == "CNAME":
                    cname_target = e.get("cname_target")
                    if cname_target:
                        line += f" | CNAME target: {cname_target}"
                    if e.get("dangling"):
                        line += " | dangling target: NXDOMAIN"
                formatted_dns_whois.append(line)
                continue

            if len(formatted_assets) >= 30:
                continue

            line = f"- [{ent_id}] {val} ({e_type} | confidence: {conf})"
            if resolves:
                line += f" -> resolves_to [C001]: {', '.join(resolves[:4])}"
            if corroborated_by:
                line += f" | sources: {', '.join(corroborated_by)}"
            if subnet_cidr:
                line += f" | subnet [C005]: {subnet_cidr}"
            if relationships:
                relationship_facts = []
                for relationship in relationships:
                    if not isinstance(relationship, dict):
                        continue

                    rule_id = relationship.get("rule_id")
                    relation_type = relationship.get("relationship")
                    if not rule_id or not relation_type:
                        continue

                    fact = f"{rule_id}:{relation_type}"
                    target_value = relationship.get("target_value")
                    if target_value:
                        fact += f" -> {target_value}"

                    evidence_sources = relationship.get("evidence_sources") or []
                    if evidence_sources:
                        fact += f" [evidence: {', '.join(str(source) for source in evidence_sources)}]"

                    relationship_facts.append(fact)

                if relationship_facts:
                    line += f" | relationships: {'; '.join(sorted(set(relationship_facts))[:8])}"

            formatted_assets.append(line)

        entities_block = (
            "\n".join(formatted_assets)
            if formatted_assets
            else "No subdomain or IP entities discovered."
        )
        dns_whois_block = (
            "\n".join(formatted_dns_whois[:20])
            if formatted_dns_whois
            else "No WHOIS or DNS email authentication records collected."
        )

        return f"""You are a Lead Security Analyst and Cyber Threat Intelligence Specialist.
Analyze the provided strictly passive reconnaissance dataset for the target domain: `{target_domain}`.

CRITICAL CONSTRAINT: Use ONLY the grounded facts provided below. Do NOT invent hostnames, IP addresses, entity IDs, ports, or vulnerabilities not present in the dataset.

--- GROUNDED RECON METRICS ---
- Target Domain: {target_domain}
- Total Subdomains Discovered: {metrics.get('total_subdomains', 0)}
- Total Active IPs Discovered: {metrics.get('total_ips', 0)}
- Multi-Source High Confidence Entities (>=0.80): {metrics.get('high_confidence_count', 0)}
- Single-Source Observations (0.60): {metrics.get('low_confidence_count', 0)}

--- DNS, EMAIL AUTH (SPF/DMARC/MX/NS) & WHOIS POSTURE ---
{dns_whois_block}

--- DISCOVERED ENTITIES & CORRELATED RELATIONSHIPS ---
{entities_block}

--- OUTPUT FORMAT ---
Write your response in clean Markdown using EXACTLY these two top-level headings (do NOT add numbers in front of them):

## Executive Summary
Write 2 concise paragraphs summarizing what was discovered across `{target_domain}` (total subdomains, IP footprint, domain registration/email security posture, and overall external attack surface) for non-technical stakeholders.

## Technical Summary
Provide a structured technical breakdown for an authorized penetration testing team using `###` subheaders for each subsection:

### High-Priority Entry Points
Identify specific discovered subdomains (such as staging, API, mail, VPN, or portal hosts) and explain what attack surface they expose for authorized validation.

### Network, DNS & Email Security Posture
Analyze the discovered IP ranges/netblocks (`C005`), shared hosting (`C003`), WHOIS registrar metadata, and SPF/DMARC/MX email authentication configuration.

### Correlated Relationships
Explain the supplied relationship facts using their rule IDs and exact entity values. Do not infer relationships that are not listed.

### Third-Party DNS Dependencies
Summarize grounded CNAME service providers and clearly flag targets marked NXDOMAIN as potential dangling DNS records. Recommend authorized ownership review only; do not suggest claiming or registering the target.

### Recommended Next Steps
Provide up to 3 prioritized follow-up actions, only when supported by the supplied findings. Each action must cite an exact grounded finding (such as a discovered host, IP, DNS record, provider, or email-authentication posture) and explain why it follows from that evidence. Omit unsupported categories rather than filling a quota; if no actionable evidence exists, say so.

This platform is strictly passive. Do not recommend HTTP/TLS/port probes, service scans, certificate handshakes, phishing or spoofing tests, or other actions that contact discovered hosts or send test messages. Suitable actions include comparing evidenced hosts with the authorized asset inventory, reviewing a flagged dangling CNAME in the authorized DNS/cloud control plane, or reviewing the recorded SPF/DMARC posture with domain administrators. Do not claim a policy is weak unless the supplied record supports it, and never recommend claiming or registering a dangling target.
"""

    @staticmethod
    def validate_grounding(
        llm_text: str,
        target_domain: str,
        grounded_entities: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Phase 7 Grounding Gate:
        Validates that every entity ID, subdomain, and IPv4 address referenced in the LLM
        output exists in the grounded dataset. Flags and quarantines any fabricated references.
        """
        clean_apex = target_domain.strip().lower().strip(".")
        allowed_values: Set[str] = {clean_apex, "1.1.1.1", "8.8.8.8", "9.9.9.9"}
        allowed_ids: Set[str] = set()
        allowed_subnet_networks: Set[str] = set()

        for ent in grounded_entities:
            val = str(ent.get("value", "")).strip().lower().strip(".")
            if val:
                allowed_values.add(val)
                # Also allow hostnames embedded inside DNS_RECORD strings (e.g., MX:aspmx.l.google.com)
                if ":" in val:
                    allowed_values.add(val.split(":", 1)[1].strip().rstrip("."))
            if ent.get("id"):
                allowed_ids.add(str(ent["id"]).strip().lower())
            subnet_cidr = ent.get("subnet_cidr")
            if subnet_cidr:
                try:
                    subnet = ipaddress.ip_network(str(subnet_cidr), strict=True)
                except ValueError:
                    pass
                else:
                    if isinstance(subnet, ipaddress.IPv4Network):
                        allowed_subnet_networks.add(str(subnet.network_address))
            for ip in ent.get("resolves_to", []):
                allowed_values.add(str(ip).strip().lower())
            for rel in ent.get("relationships", []):
                if rel.get("target_value"):
                    allowed_values.add(str(rel["target_value"]).strip().lower().strip("."))
                if rel.get("target_id"):
                    allowed_ids.add(str(rel["target_id"]).strip().lower())

        # 1. Extract all IPv4 addresses cited in LLM text
        ip_matches = set(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", llm_text))

        # 2. Extract all subdomains matching target_domain cited in LLM text
        escaped_apex = re.escape(clean_apex)
        host_matches = set(
            m.lower()
            for m in re.findall(
                rf"\b(?:[a-zA-Z0-9-]+\.)+{escaped_apex}\b",
                llm_text,
                flags=re.IGNORECASE,
            )
        )

        # 3. Extract any explicit entity ID references (e.g., ent-999 or UUIDs)
        id_matches = set(
            m.lower()
            for m in re.findall(
                r"\b(?:ent-[a-zA-Z0-9_-]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
                llm_text,
                flags=re.IGNORECASE,
            )
        )

        ungrounded_ips = sorted(
            ip for ip in ip_matches
            if ip not in allowed_values and ip not in allowed_subnet_networks
        )
        ungrounded_hosts = sorted(h for h in host_matches if h not in allowed_values)
        ungrounded_ids = sorted(eid for eid in id_matches if eid not in allowed_ids)

        violations = ungrounded_ips + ungrounded_hosts + ungrounded_ids
        passed = len(violations) == 0

        sanitized_text = llm_text
        if not passed:
            for bad_item in violations:
                pattern = re.compile(re.escape(bad_item), flags=re.IGNORECASE)
                sanitized_text = pattern.sub(
                    f"[UNVERIFIED_ENTITY_REJECTED: {bad_item}]",
                    sanitized_text,
                )

            warning_banner = (
                "\n\n---\n"
                "### Grounding Gate Audit Warning\n"
                f"The Phase 7 Grounding Gate flagged **{len(violations)}** ungrounded reference(s) "
                f"not grounded in stored entities or subnet correlations (`{', '.join(violations)}`) "
                "and quarantined them."
            )
            sanitized_text += warning_banner

        return {
            "passed": passed,
            "verified_count": len(ip_matches | host_matches | id_matches) - len(violations),
            "rejected_entities": violations,
            "sanitized_markdown": sanitized_text,
        }

    async def generate_briefing(
        self,
        target_domain: str,
        metrics: Dict[str, Any],
        top_entities: List[Dict[str, Any]],
    ) -> str:
        prompt = self._build_grounding_prompt(target_domain, metrics, top_entities)

        try:
            client = AsyncClient(host=self.ollama_host)
            response = await client.chat(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional security intelligence assistant writing an authorized assessment briefing.",
                    },
                    {"role": "user", "content": prompt},
                ],
                keep_alive="60m",
                options={
                    "temperature": 0.2,
                    "num_ctx": 4096,
                    "num_predict": 1200,
                    "num_thread": 8,
                },
            )
            raw_output = response["message"]["content"]

            # Phase 7 Grounding Gate: verify & quarantine ungrounded references before returning
            gate_result = self.validate_grounding(raw_output, target_domain, top_entities)
            return gate_result["sanitized_markdown"]

        except Exception as e:
            return f"### Executive Briefing Generation Failed\n\nUnable to connect to LLM provider at `{self.ollama_host}`: {str(e)}\n\nEnsure Ollama is running locally."