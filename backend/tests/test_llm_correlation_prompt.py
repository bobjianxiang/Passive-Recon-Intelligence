import unittest

from app.services.llm import LLMBriefingEngine


class LLMCorrelationPromptTests(unittest.TestCase):
    def test_prompt_includes_relationship_endpoints_and_evidence(self):
        engine = LLMBriefingEngine()
        prompt = engine._build_grounding_prompt(
            "example.com",
            {},
            [
                {
                    "id": "entity-1",
                    "value": "api.example.com",
                    "type": "SUBDOMAIN",
                    "confidence": 0.9,
                    "relationships": [
                        {
                            "rule_id": "C001",
                            "relationship": "RESOLVES_TO",
                            "target_value": "192.0.2.10",
                            "evidence_sources": ["subfinder"],
                        }
                    ],
                }
            ],
        )

        self.assertIn(
            "C001:RESOLVES_TO -> 192.0.2.10 [evidence: subfinder]",
            prompt,
        )
        self.assertIn("### Correlated Relationships", prompt)

    def test_next_steps_are_finding_specific_and_passive_only(self):
        engine = LLMBriefingEngine()
        prompt = engine._build_grounding_prompt(
            "example.com",
            {},
            [
                {
                    "id": "cname-1",
                    "value": "CNAME:api.example.com",
                    "type": "DNS_RECORD",
                    "record_type": "CNAME",
                    "cname_target": "orphan.azurefd.net",
                    "dangling": True,
                    "service_provider": "Azure Front Door",
                }
            ],
        )

        self.assertIn("up to 3 prioritized follow-up actions", prompt)
        self.assertIn("Each action must cite an exact grounded finding", prompt)
        self.assertIn("CNAME target: orphan.azurefd.net", prompt)
        self.assertIn("strictly passive", prompt)
        self.assertNotIn("HTTP service probing", prompt)
        self.assertNotIn("TLS/certificate inspection", prompt)
        self.assertNotIn("email spoofing", prompt)

    def test_prompt_calls_out_reserved_target_validation(self):
        engine = LLMBriefingEngine()
        prompt = engine._build_grounding_prompt(
            "sunway.test",
            {},
            [
                {
                    "id": "validation-1",
                    "value": "TARGET_VALIDATION: reserved_tld",
                    "type": "DNS_RECORD",
                    "record_type": "TARGET_VALIDATION",
                    "validation_status": "reserved_tld",
                    "validation_reason": ".test is a special-use suffix",
                }
            ],
        )

        self.assertIn("target validation: reserved_tld", prompt)
        self.assertIn("not valid for public-internet", prompt)
        self.assertIn("missing unless an EMAIL_AUTH_POSTURE record is supplied", prompt)

    def test_grounding_gate_preserves_known_subnet_cidr(self):
        subnet = "182.173.73.0/24"
        result = LLMBriefingEngine.validate_grounding(
            f"Discovered subnet: {subnet}",
            "example.com",
            [{"value": "host.example.com", "subnet_cidr": subnet}],
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["sanitized_markdown"], f"Discovered subnet: {subnet}")

    def test_grounding_gate_accepts_stored_cname_targets(self):
        target = "serviceportal.sunway.edu.my"
        result = LLMBriefingEngine.validate_grounding(
            f"sspr.sunway.edu.my points to {target}",
            "sunway.edu.my",
            [
                {
                    "id": "cname-1",
                    "value": "CNAME:sspr.sunway.edu.my",
                    "type": "DNS_RECORD",
                    "record_type": "CNAME",
                    "cname_target": target,
                    "cname_chain": [
                        {
                            "source": "sspr.sunway.edu.my",
                            "target": target,
                        }
                    ],
                }
            ],
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["rejected_entities"], [])
        self.assertEqual(
            result["sanitized_markdown"],
            f"sspr.sunway.edu.my points to {target}",
        )

    def test_grounding_gate_still_rejects_unknown_subnet(self):
        result = LLMBriefingEngine.validate_grounding(
            "Discovered subnet: 182.173.74.0/24",
            "example.com",
            [{"value": "host.example.com", "subnet_cidr": "182.173.73.0/24"}],
        )

        self.assertFalse(result["passed"])
        self.assertIn(
            "[UNVERIFIED_ENTITY_REJECTED: 182.173.74.0]/24",
            result["sanitized_markdown"],
        )


if __name__ == "__main__":
    unittest.main()
