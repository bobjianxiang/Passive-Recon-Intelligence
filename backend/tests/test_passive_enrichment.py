import asyncio
import unittest
import dns.resolver
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.recon.dns_auth import (
    DnsAuthPassiveModule,
    _is_special_use_domain,
    classify_service_provider,
)
from app.services.asn_enrichment import (
    ASNEnrichmentService,
    build_cymru_query_name,
    parse_cymru_record,
)


class CNAMEProviderTests(unittest.TestCase):
    def test_known_provider_suffixes_are_matched_at_domain_boundaries(self):
        cases = {
            "tenant.sharepoint.com": "Microsoft 365",
            "edge.azurefd.net": "Azure Front Door",
            "d123.cloudfront.net": "AWS",
            "site.cloudflare.net": "Cloudflare",
            "site.unbouncepages.com": "Unbounce",
        }
        for hostname, provider in cases.items():
            with self.subTest(hostname=hostname):
                self.assertEqual(classify_service_provider(hostname), provider)

        self.assertIsNone(classify_service_provider("azurefd.net.attacker.example"))


class CNAMEEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_cname_to_nxdomain_is_returned_as_dangling_dns_record(self):
        class FakeNXDOMAIN(Exception):
            pass

        class FakeNoAnswer(Exception):
            pass

        class FakeResolver:
            async def resolve(self, name, record_type):
                if name == "api.example.com" and record_type == "CNAME":
                    return [SimpleNamespace(target="missing.azurefd.net.")]
                if name == "missing.azurefd.net" and record_type == "CNAME":
                    raise FakeNXDOMAIN()
                if record_type == "A":
                    raise FakeNoAnswer()
                raise FakeNoAnswer()

        module = DnsAuthPassiveModule()
        with patch("dns.resolver.NXDOMAIN", FakeNXDOMAIN), patch(
            "dns.resolver.NoAnswer", FakeNoAnswer
        ):
            records, warnings = await module._discover_cname_records(
                FakeResolver(),
                "example.com",
                ["api.example.com"],
            )

        self.assertEqual(warnings, [])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].entity_type, "DNS_RECORD")
        self.assertTrue(records[0].raw_record["dangling"])
        self.assertEqual(records[0].raw_record["service_provider"], "Azure Front Door")

    async def test_reserved_target_is_identified_without_claiming_missing_email_records(self):
        class FakeResolver:
            nameservers = []
            lifetime = 0

            async def resolve(self, _name, _record_type):
                raise dns.resolver.NXDOMAIN()

        with patch(
            "app.recon.dns_auth.dns.asyncresolver.Resolver",
            return_value=FakeResolver(),
        ):
            result = await DnsAuthPassiveModule().run("sunway.test", uuid4())

        validation = next(
            record for record in result.raw_observations
            if record.raw_record.get("record_type") == "TARGET_VALIDATION"
        )
        self.assertEqual(validation.raw_record["validation_status"], "reserved_tld")
        self.assertFalse(any(
            record.raw_record.get("record_type") == "EMAIL_AUTH_SUMMARY"
            for record in result.raw_observations
        ))

    async def test_nxdomain_target_is_identified_without_email_posture_claims(self):
        class FakeResolver:
            nameservers = []
            lifetime = 0

            async def resolve(self, _name, _record_type):
                raise dns.resolver.NXDOMAIN()

        with patch(
            "app.recon.dns_auth.dns.asyncresolver.Resolver",
            return_value=FakeResolver(),
        ):
            result = await DnsAuthPassiveModule().run("missing.example.com", uuid4())

        validation = next(
            record for record in result.raw_observations
            if record.raw_record.get("record_type") == "TARGET_VALIDATION"
        )
        self.assertEqual(validation.raw_record["validation_status"], "nxdomain")
        self.assertFalse(any(
            record.raw_record.get("record_type") == "EMAIL_AUTH_SUMMARY"
            for record in result.raw_observations
        ))


class TargetDomainClassificationTests(unittest.TestCase):
    def test_reserved_special_use_tlds_are_not_public_recon_targets(self):
        for domain in ("sunway.test", "example.invalid", "host.example"):
            with self.subTest(domain=domain):
                self.assertTrue(_is_special_use_domain(domain))
        self.assertFalse(_is_special_use_domain("example.com"))


class ASNEnrichmentTests(unittest.TestCase):
    def test_builds_cymru_queries_and_parses_origin_records(self):
        self.assertEqual(
            build_cymru_query_name("1.2.3.4"),
            "4.3.2.1.origin.asn.cymru.com",
        )
        self.assertEqual(
            build_cymru_query_name("2001:db8::1"),
            "1.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.origin6.asn.cymru.com",
        )
        self.assertEqual(
            parse_cymru_record("15169 | 8.8.8.0/24 | US | arin | 2000-03-30 | GOOGLE, US"),
            {
                "asn": "AS15169",
                "asn_cidr": "8.8.8.0/24",
                "provider": "GOOGLE, US",
                "asn_country": "US",
                "asn_registry": "arin",
            },
        )

    def test_enrichment_persists_route_attributes_without_overwriting_scan_data(self):
        class FakeSelect:
            def where(self, *_conditions):
                return self

        class FakeRdata:
            strings = [
                b"15169 | 8.8.8.0/24 | US | arin | 2000-03-30 | GOOGLE, US"
            ]

        class FakeResolver:
            async def resolve(self, query_name, record_type):
                self.query = (query_name, record_type)
                return [FakeRdata()]

        class FakeResult:
            def scalars(self):
                return self

            def all(self):
                return [entity]

        class FakeDatabase:
            async def execute(self, _statement):
                return FakeResult()

        entity = SimpleNamespace(
            canonical_value="8.8.8.8",
            attributes={"subnet_cidr": "8.8.8.0/24"},
        )
        resolver = FakeResolver()

        with patch("app.services.asn_enrichment.select", return_value=FakeSelect()), patch(
            "app.services.asn_enrichment.dns.asyncresolver.Resolver",
            return_value=resolver,
        ):
            warnings = asyncio.run(
                ASNEnrichmentService.enrich_job_ips(uuid4(), FakeDatabase())
            )

        self.assertEqual(warnings, [])
        self.assertEqual(resolver.query, ("8.8.8.8.origin.asn.cymru.com", "TXT"))
        self.assertEqual(entity.attributes["asn"], "AS15169")
        self.assertEqual(entity.attributes["asn_cidr"], "8.8.8.0/24")
        self.assertEqual(entity.attributes["provider"], "GOOGLE, US")
        self.assertEqual(entity.attributes["subnet_cidr"], "8.8.8.0/24")


if __name__ == "__main__":
    unittest.main()
