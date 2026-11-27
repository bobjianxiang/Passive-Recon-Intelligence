import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.api.endpoints import summary
from app.models.recon import EntityType


class FakeResult:
    def __init__(self, value=None, values=None):
        self.value = value
        self.values = values or []

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.values


class FakeDatabase:
    def __init__(self, job, entities):
        self.job_result = FakeResult(value=job)
        self.entity_result = FakeResult(values=entities)
        self.execute_count = 0
        self.committed = False

    async def execute(self, _statement):
        self.execute_count += 1
        if self.execute_count == 1:
            return self.job_result
        return self.entity_result

    async def commit(self):
        self.committed = True


class SummaryReadOnlyLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_briefing_does_not_run_llm_for_historical_lookup(self):
        job_id = uuid4()
        job = SimpleNamespace(
            id=job_id,
            target_domain="example.com",
            briefing_markdown=None,
        )
        entity = SimpleNamespace(
            id=uuid4(),
            canonical_value="api.example.com",
            entity_type=EntityType.SUBDOMAIN,
            confidence=0.9,
            attributes={},
        )
        db = FakeDatabase(job, [entity])

        with patch.object(summary, "LLMBriefingEngine") as llm_engine:
            result = await summary.generate_job_security_briefing(
                job_id,
                generate_if_missing=False,
                db=db,
            )

        llm_engine.assert_not_called()
        self.assertFalse(db.committed)
        self.assertEqual(len(result["entities"]), 1)
        self.assertEqual(result["briefing_status"], "missing")
        self.assertIn("No saved AI briefing", result["briefing_markdown"])

    async def test_high_confidence_metric_counts_only_discovered_assets(self):
        job_id = uuid4()
        job = SimpleNamespace(
            id=job_id,
            target_domain="example.com",
            briefing_markdown=None,
        )
        entities = [
            SimpleNamespace(
                id=uuid4(),
                canonical_value="example.com",
                entity_type=EntityType.DOMAIN,
                confidence=1.0,
                attributes={},
            ),
            SimpleNamespace(
                id=uuid4(),
                canonical_value="EMAIL_AUTH_POSTURE: SPF=MISSING",
                entity_type=EntityType.DNS_RECORD,
                confidence=0.95,
                attributes={},
            ),
            SimpleNamespace(
                id=uuid4(),
                canonical_value="example.com",
                entity_type=EntityType.SUBDOMAIN,
                confidence=0.6,
                attributes={},
            ),
            SimpleNamespace(
                id=uuid4(),
                canonical_value="api.example.com",
                entity_type=EntityType.SUBDOMAIN,
                confidence=0.9,
                attributes={},
            ),
            SimpleNamespace(
                id=uuid4(),
                canonical_value="legacy.example.com",
                entity_type=EntityType.SUBDOMAIN,
                confidence=0.6,
                attributes={},
            ),
        ]
        db = FakeDatabase(job, entities)

        with patch.object(summary, "LLMBriefingEngine") as llm_engine:
            llm_engine.return_value.generate_briefing = AsyncMock(return_value="Briefing")
            result = await summary.generate_job_security_briefing(job_id, db=db)

        self.assertEqual(result["metrics"]["high_confidence_count"], 1)
        self.assertEqual(result["metrics"]["low_confidence_count"], 1)
        self.assertEqual(result["metrics"]["total_subdomains"], 2)


if __name__ == "__main__":
    unittest.main()
