import asyncio
import json
import time
from datetime import datetime
from uuid import UUID
from app.recon.base import ModuleRunResult, ParsedRecord

class SubfinderPassiveModule:
    def __init__(self, timeout_seconds: int = 120):
        self.module_name = "subfinder"
        self.timeout_seconds = timeout_seconds

    async def run(self, target_domain: str, job_id: UUID) -> ModuleRunResult:
        started_at = datetime.utcnow()
        start_time = time.time()
        observations: list[ParsedRecord] = []
        seen_hosts = set()

        cmd = [
            "subfinder",
            "-d", target_domain,
            "-silent",
            "-json",
            "-t", "100",        # Maximize thread pool (default is 10)
            "-c", "50",         # Maximize concurrent HTTP requests
            "-timeout", "5",    # 5s aggressive timeout per API provider
            "-max-time", "110"  # 110s max hard cap for binary execution
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            timed_out = False
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), 
                    timeout=float(self.timeout_seconds)
                )
            except asyncio.TimeoutError:
                timed_out = True
                proc.kill()
                stdout, stderr = await proc.communicate()

            # Parse whatever output was generated (even on process timeout)
            if stdout:
                for line in stdout.decode("utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        host = data.get("host", "").strip().lower()
                        if host and host not in seen_hosts:
                            seen_hosts.add(host)
                            observations.append(
                                ParsedRecord(
                                    entity_type="SUBDOMAIN",
                                    canonical_value=host,
                                    raw_record=data
                                )
                            )
                    except json.JSONDecodeError:
                        continue

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
                        f"Subfinder process timed out after {self.timeout_seconds}s "
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