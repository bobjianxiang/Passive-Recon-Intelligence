import unittest
from unittest.mock import patch
from uuid import uuid4

from app.recon.base import ModuleRunResult
from app.recon.amass import AmassPassiveModule
from app.recon.subfinder import SubfinderPassiveModule
from app.recon.waybackurls import WaybackurlsPassiveModule


class ReconModuleResultContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_amass_uses_fixed_medium_limits(self):
        class FakeProcess:
            returncode = 0

            async def communicate(self):
                return b"", b""

        with patch(
            "app.recon.amass.asyncio.create_subprocess_exec",
            return_value=FakeProcess(),
        ) as create_process:
            result = await AmassPassiveModule().run("example.com", uuid4())

        self.assertIsInstance(result, ModuleRunResult)
        self.assertEqual(result.status, "success")
        command = create_process.call_args.args
        self.assertEqual(command[command.index("-timeout") + 1], "1")
        self.assertEqual(
            command[command.index("-max-dns-queries") + 1],
            "250",
        )

    async def test_subfinder_returns_shared_result_when_binary_is_unavailable(self):
        with patch(
            "app.recon.subfinder.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("subfinder not installed"),
        ):
            result = await SubfinderPassiveModule().run("example.com", uuid4())

        self.assertIsInstance(result, ModuleRunResult)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.errors, ["subfinder not installed"])
        self.assertEqual(result.warnings, [])

    async def test_waybackurls_returns_shared_result_when_binary_is_unavailable(self):
        with patch(
            "app.recon.waybackurls.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("waybackurls not installed"),
        ):
            result = await WaybackurlsPassiveModule().run("example.com", uuid4())

        self.assertIsInstance(result, ModuleRunResult)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.errors, ["waybackurls not installed"])
        self.assertEqual(result.warnings, [])


if __name__ == "__main__":
    unittest.main()
