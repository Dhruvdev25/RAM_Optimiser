import threading
import unittest

from ram_optimiser.core import (
    MemoryMeasurement, OperationGate, ProcessIdentity, format_bytes,
    identity_matches, is_protected_process, memory_percent,
)


class CoreTests(unittest.TestCase):
    def test_memory_calculations_and_formatting(self):
        self.assertEqual(memory_percent(100, 25), 25.0)
        self.assertIsNone(memory_percent(0, 25))
        self.assertEqual(format_bytes(1024**3), "1.0 GiB")
        self.assertEqual(format_bytes(None), "Unavailable")
        self.assertEqual(MemoryMeasurement(100, 140).available_delta, 40)
        self.assertIsNone(MemoryMeasurement(None, 140).available_delta)

    def test_protection_and_process_identity(self):
        self.assertTrue(is_protected_process("svchost.exe", 90, own_pid=101))
        self.assertTrue(is_protected_process("MemCompression", 90, own_pid=101))
        self.assertTrue(is_protected_process("TiWorker.exe", 90, own_pid=101))
        self.assertTrue(is_protected_process("my-app.exe", 101, own_pid=101))
        self.assertTrue(is_protected_process("Editor.exe", 90, 101, ["editor.exe"]))
        self.assertFalse(is_protected_process("editor.exe", 90, 101))
        identity = ProcessIdentity(44, 1234.5)
        self.assertTrue(identity_matches(identity, 44, 1234.5))
        self.assertFalse(identity_matches(identity, 44, 999.0))
        self.assertFalse(identity_matches(identity, 45, 1234.5))
        self.assertFalse(identity_matches(identity, 44, None))

    def test_operation_gate_allows_only_one_concurrent_operation(self):
        gate = OperationGate()
        started = threading.Event()
        release = threading.Event()
        accepted = []

        def first():
            if gate.try_enter():
                accepted.append("first")
                started.set()
                release.wait(2)
                gate.leave()

        owner = threading.Thread(target=first)
        owner.start()
        self.assertTrue(started.wait(2))
        contenders = [threading.Thread(target=lambda: accepted.append("other") if gate.try_enter() else None)
                      for _ in range(12)]
        for thread in contenders:
            thread.start()
        for thread in contenders:
            thread.join(2)
        release.set()
        owner.join(2)
        self.assertEqual(accepted, ["first"])
        self.assertFalse(gate.active)


if __name__ == "__main__":
    unittest.main()
