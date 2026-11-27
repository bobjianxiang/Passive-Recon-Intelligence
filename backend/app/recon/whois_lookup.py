import asyncio
import re
import shutil
import time
from datetime import datetime
from uuid import UUID
import whois
from app.recon.base import ModuleRunResult, ParsedRecord


class WhoisPassiveModule:
    name: str = "whois_lookup"
    version: str = "1.1.0"

    @staticmethod
    def _normalize_date(val) -> str | None:
        if isinstance(val, list) and val:
            val = val[0]
        if isinstance(val, datetime):
            return val.strftime("%Y-%m-%d")
        return str(val).strip() if val else None

    @staticmethod
    async def _cli_whois_fallback(domain: str) -> dict:
        """Fallback to system whois binary (e.g., against whois.mynic.my) if python-whois times out."""
        if not shutil.which("whois"):
            return {}
        cmd = ["whois", "-h", "whois.mynic.my", domain] if domain.endswith(".my") else ["whois", domain]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
        text = stdout.decode("utf-8", errors="ignore")

        reg_match = re.search(r"(?:Registrar|Sponsoring Registrar)\s*:\s*(.+)", text, re.I)
        created_match = re.search(r"(?:Creation Date|Registered On|Record Created)\s*:\s*([0-9T:\-Z]+)", text, re.I)
        expiry_match = re.search(r"(?:Registry Expiry Date|Expiration Date|Expiry Date|Record Expires)\s*:\s*([0-9T:\-Z]+)", text, re.I)

        return {
            "registrar": reg_match.group(1).strip() if reg_match else None,
            "creation_date": created_match.group(1).strip()[:10] if created_match else None,
            "expiration_date": expiry_match.group(1).strip()[:10] if expiry_match else None,
        }

    async def run(self, target: str, job_id: UUID) -> ModuleRunResult:
        started_at = datetime.utcnow()
        start_time = time.time()

        raw_records: list[ParsedRecord] = []
        errors: list[str] = []
        warnings: list[str] = []
        status = "success"

        clean_target = target.strip().lower().strip(".")

        registrar = None
        creation_date = None
        expiration_date = None
        org = None
        country = None
        name_servers: list[str] = []

        try:
            loop = asyncio.get_running_loop()
            w = await asyncio.wait_for(
                loop.run_in_executor(None, whois.whois, clean_target),
                timeout=30.0,
            )

            registrar = w.registrar[0] if isinstance(w.registrar, list) else w.registrar
            creation_date = self._normalize_date(w.creation_date)
            expiration_date = self._normalize_date(w.expiration_date)
            org = w.org[0] if isinstance(w.org, list) else getattr(w, "org", None)
            country = w.country[0] if isinstance(w.country, list) else getattr(w, "country", None)

            if getattr(w, "name_servers", None):
                raw_ns = w.name_servers if isinstance(w.name_servers, list) else [w.name_servers]
                name_servers = sorted({str(ns).lower().rstrip(".") for ns in raw_ns if ns})

        except Exception as primary_err:
            warnings.append(f"Primary python-whois lookup delayed ({primary_err}); trying CLI fallback.")
            try:
                fallback = await self._cli_whois_fallback(clean_target)
                registrar = fallback.get("registrar")
                creation_date = fallback.get("creation_date")
                expiration_date = fallback.get("expiration_date")
            except Exception as fb_err:
                warnings.append(f"WHOIS registry unreachable: {fb_err}")

        if registrar:
            raw_records.append(ParsedRecord(
                entity_type="DNS_RECORD",
                canonical_value=f"WHOIS_REGISTRAR:{str(registrar).strip()}",
                raw_record={
                    "record_type": "WHOIS",
                    "registrar": str(registrar).strip(),
                    "organization": str(org).strip() if org else None,
                    "country": str(country).strip() if country else None,
                    "creation_date": creation_date,
                    "expiration_date": expiration_date,
                    "name_servers": name_servers,
                    "source": "whois_lookup",
                },
            ))

        if expiration_date or creation_date:
            raw_records.append(ParsedRecord(
                entity_type="DNS_RECORD",
                canonical_value=f"WHOIS_LIFECYCLE:created={creation_date or 'N/A'},expires={expiration_date or 'N/A'}",
                raw_record={
                    "record_type": "WHOIS_DATES",
                    "creation_date": creation_date,
                    "expiration_date": expiration_date,
                    "source": "whois_lookup",
                },
            ))

        if not raw_records:
            status = "partial_success"
            warnings.append("WHOIS metadata unavailable or rate-limited by registry.")

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
            errors=errors,
        )