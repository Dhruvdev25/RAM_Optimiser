import tempfile
import unittest
from pathlib import Path

from ram_optimiser.history import HistoryStore
from ram_optimiser.settings import Settings, SettingsStore


class StorageTests(unittest.TestCase):
    def test_settings_persistence_and_malformed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = SettingsStore(path)
            settings = Settings(refresh_seconds=4, protected_apps=["editor.exe"], eligible_apps=["browser.exe"],
                                game_profiles=["C:/Games/game.exe"], minimize_during_game=True)
            store.save(settings)
            loaded = store.load()
            self.assertEqual(loaded.refresh_seconds, 4)
            self.assertEqual(loaded.protected_apps, ["editor.exe"])
            self.assertEqual(loaded.eligible_apps, ["browser.exe"])
            self.assertEqual(loaded.game_profiles, ["C:/Games/game.exe"])
            self.assertTrue(loaded.minimize_during_game)
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual(SettingsStore(path).load().refresh_seconds, 2)

    def test_history_samples_boosts_sessions_and_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HistoryStore(Path(directory) / "history.sqlite3", retention_days=2)
            store.record_sample(70.5, 22.0, None)
            store.record_boost("Quick Boost", 1000, 1100, 2, 1, 1, 0.4, [{"success": True}])
            session = store.start_session("game.exe")
            store.end_session(session, 3661)
            self.assertEqual(len(store.recent_samples()), 1)
            self.assertEqual(store.recent_samples()[0][1:4], (70.5, 22.0, None))
            self.assertEqual(store.recent_boosts()[0][1], "Quick Boost")
            self.assertEqual(store.recent_sessions()[0][2:], ("game.exe", 3661))
            store.clear()
            self.assertEqual(store.recent_samples(), [])
            self.assertEqual(store.recent_boosts(), [])
            self.assertEqual(store.recent_sessions(), [])


if __name__ == "__main__":
    unittest.main()
