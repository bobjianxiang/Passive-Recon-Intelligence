import unittest

from app.recon.theharvester import TheHarvesterPassiveModule
from app.services.entity_validation import is_valid_entity_value


class TheHarvesterParsingTests(unittest.TestCase):
    def test_only_target_hosts_and_valid_ips_are_classified(self):
        records = TheHarvesterPassiveModule._parse_hosts(
            [
                "198.51.100.10:76be6edb1c464e32b4f6cf92d6cc8c2b.unbouncepages.com",
                "198.51.100.11:live-main-h5d2htfje7dqfhg6.z01.azurefd.net",
                "api.sunway.edu.my:203.0.113.8",
                "sunway.edu.my.attacker.com:203.0.113.9",
            ],
            "sunway.edu.my",
        )
        entities = {(record.entity_type, record.canonical_value) for record in records}

        self.assertIn(("SUBDOMAIN", "api.sunway.edu.my"), entities)
        self.assertIn(("IP_ADDRESS", "203.0.113.8"), entities)
        self.assertFalse(any(
            value in {
                "76be6edb1c464e32b4f6cf92d6cc8c2b.unbouncepages.com",
                "live-main-h5d2htfje7dqfhg6.z01.azurefd.net",
            }
            for _, value in entities
        ))
        self.assertNotIn(("SUBDOMAIN", "sunway.edu.my.attacker.com"), entities)

    def test_invalid_persisted_ip_rows_are_filtered_from_entity_responses(self):
        self.assertTrue(is_valid_entity_value("IP_ADDRESS", "203.0.113.8"))
        self.assertFalse(is_valid_entity_value(
            "IP_ADDRESS",
            "76be6edb1c464e32b4f6cf92d6cc8c2b.unbouncepages.com",
        ))
        self.assertTrue(is_valid_entity_value(
            "SUBDOMAIN",
            "76be6edb1c464e32b4f6cf92d6cc8c2b.unbouncepages.com",
        ))


if __name__ == "__main__":
    unittest.main()
