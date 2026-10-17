"""Checks that the demonstration runs without real configuration or devices."""

import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


class DemoTest(unittest.TestCase):
    def test_demo_api_does_not_load_real_config(self):
        with patch.dict(os.environ, {
            "MONITOREO_DEMO": "1",
            "MONITOREO_CONFIG": "missing-config.yaml",
        }):
            sys.modules.pop("app", None)
            app = importlib.import_module("app")
            client = app.app.test_client()
            config = client.get("/api/config").get_json()
            state = client.get("/api/state").get_json()
            history = client.get(
                "/api/history?entity=Router-Lab&metric=cpu_load"
            ).get_json()
            self.assertEqual(config["routers"][0]["name"], "Router-Lab")
            self.assertTrue(state["readings"])
            self.assertEqual(len(history), 6)
            self.assertFalse(any(r["metric"] == "ip" for r in state["readings"]))
            self.assertEqual(
                client.get("/api/history?hours=invalid").status_code, 400
            )


if __name__ == "__main__":
    unittest.main()
