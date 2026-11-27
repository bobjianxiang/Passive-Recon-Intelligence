import asyncio
import os
import time
import re
from datetime import datetime
from uuid import UUID
from app.recon.base import PassiveReconModule, ModuleRunResult, ParsedRecord


AMASS_TIMEOUT_MINUTES = "1"
AMASS_PROCESS_TIMEOUT_SECONDS = 90
AMASS_MAX_DNS_QUERIES = 250


class AmassPassiveModule:
    name: str = "amass"
    version: str = "4.2.0"

    async def run(
        self,
        target: str,
        job_id: UUID,
    ) -> ModuleRunResult:
        started_at = datetime.utcnow()
        start_time = time.time()
        
        output_file = f"/tmp/amass_{job_id}.txt"
        cmd = [
            "amass", "enum",
            "-passive",
            "-d", target,
            "-timeout", AMASS_TIMEOUT_MINUTES,
            "-max-dns-queries", str(AMASS_MAX_DNS_QUERIES),
            "-r", "1.1.1.1,8.8.8.8,9.9.9.9", # Fast public resolvers to bypass local DNS lag
            "-o", output_file
        ]
        
        raw_records: list[ParsedRecord] = []
        errors: list[str] = []
        warnings: list[str] = []
        status = "success"
        timed_out = False
        stdout = b""

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=AMASS_PROCESS_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                timed_out = True
                proc.kill()
                await proc.wait()
                warnings.append(
                    f"Amass reached {AMASS_PROCESS_TIMEOUT_SECONDS}s execution cap; "
                    "harvesting partial output."
                )

            # Parse output file or stdout even if process timed out
            lines_to_parse = []
            if os.path.exists(output_file):
                with open(output_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines_to_parse = f.readlines()
                os.remove(output_file)
            elif stdout:
                lines_to_parse = stdout.decode("utf-8", errors="ignore").splitlines()

            ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
            domain_pattern = re.compile(r'\b(?:[a-zA-Z0-9-]+\.)+' + re.escape(target) + r'\b')
            seen_values = set()

            for line in lines_to_parse:
                line_str = line.strip()
                if not line_str:
                    continue

                domains = domain_pattern.findall(line_str)
                for domain in domains:
                    clean_domain = domain.lower().strip(".")
                    if clean_domain not in seen_values:
                        seen_values.add(clean_domain)
                        raw_records.append(ParsedRecord(
                            entity_type="SUBDOMAIN",
                            canonical_value=clean_domain,
                            raw_record={"discovered_string": line_str, "source": "amass"}
                        ))

                ips = ip_pattern.findall(line_str)
                for ip in ips:
                    if ip not in seen_values:
                        seen_values.add(ip)
                        raw_records.append(ParsedRecord(
                            entity_type="IP_ADDRESS",
                            canonical_value=ip,
                            raw_record={"discovered_string": line_str, "source": "amass"}
                        ))

            if timed_out:
                status = "partial_success" if raw_records else "failed"
                if not raw_records:
                    errors.append(
                        f"Amass module execution timed out after "
                        f"{AMASS_PROCESS_TIMEOUT_SECONDS}s with no findings."
                    )

        except Exception as e:
            status = "failed"
            errors.append(str(e))
            if os.path.exists(output_file):
                os.remove(output_file)

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