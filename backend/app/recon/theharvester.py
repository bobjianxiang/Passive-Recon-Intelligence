import asyncio
import os
import json
import time
from datetime import datetime
from uuid import UUID
from app.recon.base import ModuleRunResult, ParsedRecord
from app.services.entity_validation import normalize_ip_address

class TheHarvesterPassiveModule:
    name: str = "theharvester"
    version: str = "4.6.0"

    @staticmethod
    def _parse_hosts(hosts: list[str], target: str) -> list[ParsedRecord]:
        target_domain = target.lower().strip(".")
        seen_values = set()
        raw_records = []

        for host in hosts:
            if not isinstance(host, str):
                continue

            for part in host.split(":"):
                value = part.strip().strip("[]")
                if not value:
                    continue

                ip_address = normalize_ip_address(value)
                if ip_address is not None:
                    entity_type = "IP_ADDRESS"
                    canonical_value = ip_address
                else:
                    domain = value.lower().strip(".")
                    if domain == target_domain:
                        entity_type = "DOMAIN"
                    elif domain.endswith(f".{target_domain}"):
                        entity_type = "SUBDOMAIN"
                    else:
                        continue
                    canonical_value = domain

                key = (entity_type, canonical_value)
                if key in seen_values:
                    continue
                seen_values.add(key)
                raw_records.append(ParsedRecord(
                    entity_type=entity_type,
                    canonical_value=canonical_value,
                    raw_record={"raw_host": host, "source": "theharvester"}
                ))

        return raw_records

    async def run(self, target: str, job_id: UUID) -> ModuleRunResult:
        started_at = datetime.utcnow()
        start_time = time.time()
        
        output_file_prefix = f"/tmp/theharvester_{job_id}"
        json_output_file = f"{output_file_prefix}.json"
        xml_output_file = f"{output_file_prefix}.xml"
        
        # Fast, non-CAPTCHA passive sources + 200 result cap per source
        cmd = [
            "theHarvester",
            "-d", target,
            "-b", "crtsh,certspotter,duckduckgo,hackertarget,rapiddns,urlscan",
            "-l", "200",
            "-f", output_file_prefix
        ]
        
        raw_records: list[ParsedRecord] = []
        errors: list[str] = []
        warnings: list[str] = []
        status = "success"
        timed_out = False

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90.0)
            except asyncio.TimeoutError:
                timed_out = True
                proc.kill()
                await proc.wait()
                warnings.append("theHarvester reached 90s execution cap; checking for partial output.")

            if os.path.exists(json_output_file):
                with open(json_output_file, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                
                # Parse discovered hosts & IP mappings
                raw_records.extend(self._parse_hosts(data.get("hosts", []), target))
            elif not timed_out:
                warnings.append("theHarvester completed without producing a JSON output file.")

            if timed_out:
                status = "partial_success" if raw_records else "failed"
                if not raw_records:
                    errors.append("theHarvester execution timed out after 90s with no findings.")

        except Exception as e:
            status = "failed"
            errors.append(str(e))
        finally:
            for temp_file in (json_output_file, xml_output_file):
                if os.path.exists(temp_file):
                    os.remove(temp_file)

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