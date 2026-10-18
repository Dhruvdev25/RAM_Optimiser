import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ram_optimiser import services
from ram_optimiser.core import MIB, ProcessIdentity
from ram_optimiser.services import ProcessRecord


@unittest.skipIf(services.psutil is None, "psutil is required for Boost service tests")
class BoostTests(unittest.TestCase):
    def test_result_uses_measured_available_memory_and_operation_counts(self):
        candidate = SimpleNamespace(identity=object(), pid=77, name="selected-app.exe")
        memory_samples = [SimpleNamespace(available=800), SimpleNamespace(available=920)]
        with patch.object(services.psutil, "virtual_memory", side_effect=memory_samples), \
             patch.object(services, "_safe_candidates", return_value=[candidate, candidate]), \
             patch.object(services, "trim_process", side_effect=[(True, "accepted"), (False, "denied")]):
            result = services.run_boost("Quick Boost")
        self.assertEqual(result["before_available"], 800)
        self.assertEqual(result["after_available"], 920)
        self.assertEqual(result["available_delta"], 120)
        self.assertEqual(result["attempted"], 2)
        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(len(result["details"]), 2)

    def test_candidate_selection_respects_protection_exclusion_and_eligible_list(self):
        def record(pid, name, mib, protected=False):
            return ProcessRecord(pid, name, mib * MIB, 0.0, "running", protected,
                                 1000.0 + pid, "Unavailable", "Unavailable")

        records = [record(1, "critical.exe", 500, True),
                   record(2, "excluded.exe", 500), record(3, "small.exe", 30),
                   record(4, "eligible.exe", 30), record(5, "large.exe", 150)]
        with patch.object(services, "list_processes", return_value=records):
            selected = services._safe_candidates("Quick Boost", ["critical.exe"], ["excluded.exe"], ["eligible.exe"])
        self.assertEqual([item.name for item in selected], ["eligible.exe", "large.exe"])

    def test_stale_process_identity_is_rejected_before_action(self):
        fake_process = SimpleNamespace(create_time=lambda: 900.0)
        with patch.object(services.psutil, "Process", return_value=fake_process):
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                services._validate_identity(ProcessIdentity(321, 100.0))

    def test_process_list_protects_other_users_and_unverified_owners(self):
        def fake_proc(pid, username):
            return SimpleNamespace(
                info={"pid": pid, "name": f"app-{pid}.exe", "memory_info": SimpleNamespace(rss=10),
                      "status": "running", "create_time": 1000.0 + pid,
                      "exe": "Unavailable", "username": username},
                cpu_percent=lambda interval=None: 0.0,
            )

        with patch.object(services, "_current_username", return_value="DOMAIN\\current"), \
             patch.object(services.psutil, "process_iter", return_value=[
                 fake_proc(41, "DOMAIN\\current"), fake_proc(42, "DOMAIN\\another"),
                 fake_proc(43, None),
             ]):
            records = services.list_processes()
        self.assertEqual([record.protected for record in records], [False, True, True])

    def test_actions_reject_processes_owned_by_another_user(self):
        fake_process = SimpleNamespace(
            create_time=lambda: 1234.5,
            name=lambda: "editor.exe",
            username=lambda: "DOMAIN\\another",
        )
        with patch.object(services.psutil, "Process", return_value=fake_process), \
             patch.object(services, "_current_username", return_value="DOMAIN\\current"):
            with self.assertRaisesRegex(PermissionError, "current Windows user"):
                services._validate_identity(ProcessIdentity(321, 1234.5))


if __name__ == "__main__":
    unittest.main()
