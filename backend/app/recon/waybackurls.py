import asyncio
import time
from datetime import datetime
from uuid import UUID
from urllib.parse import urlparse
from app.recon.base import ModuleRunResult, ParsedRecord

class WaybackurlsPassiveModule:
    def __init__(self, timeout_seconds: int = 60):
        self.module_name = "waybackurls"
        self.timeout_seconds = timeout_seconds

    async def run(self, target_domain: str, job_id: UUID) -> ModuleRunResult:
        started_at = datetime.utcnow()
        start_time = time.time()
        observations: list[ParsedRecord] = []
        seen_hosts = set()
        target_clean = target_domain.strip().lower()

        try:
            proc = await asyncio.create_subprocess_exec(
                "waybackurls",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            timed_out = False
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=f"{target_clean}\n".encode()),
                    timeout=float(self.timeout_seconds)
                )
            except asyncio.TimeoutError:
                timed_out = True
                proc.kill()
                stdout, stderr = await proc.communicate()

            # Parse buffered stdout even if waybackurls hit the timeout cap on massive archives
            if stdout:
                for line in stdout.decode("utf-8", errors="ignore").splitlines():
                    raw_url = line.strip()
                    if not raw_url:
                        continue
                    
                    parsed = urlparse(raw_url)
                    hostname = parsed.netloc.split(":")[0].lower().strip(".")

                    # Strict domain/subdomain boundary check
                    if (
                        hostname
                        and hostname != target_clean
                        and hostname.endswith(f".{target_clean}")
                        and hostname not in seen_hosts
                    ):
                        seen_hosts.add(hostname)
                        observations.append(
                            ParsedRecord(
                                entity_type="SUBDOMAIN",
                                canonical_value=hostname,
                                raw_record={"url": raw_url, "source": "wayback_archive"}
                            )
                        )

            finished_at = datetime.utcnow()
            duration_ms = int((time.time() - start_time) * 1000)

            if timed_out:
                return ModuleRunResult(
                    module=self.module_name,
                    status="partial_success" if observations else "timeout",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    raw_observations=observations,
                    errors=[
                        f"Waybackurls timed out after {self.timeout_seconds}s "
                        f"(recovered {len(observations)} subdomains)"
                    ]
                )

            return ModuleRunResult(
                module=self.module_name,
                status="success",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                raw_observations=observations,
                errors=[stderr.decode().strip()] if stderr and proc.returncode != 0 else []
            )

        except Exception as e:
            finished_at = datetime.utcnow()
            duration_ms = int((time.time() - start_time) * 1000)
            return ModuleRunResult(
                module=self.module_name,
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                raw_observations=[],
                errors=[str(e)]
            )