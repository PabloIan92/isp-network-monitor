#!/usr/bin/env python3
"""Automated tests for isp-network-monitor demo mode and REST API."""
import os
import sys
import unittest
from pathlib import Path

# Add project root and src to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from src.demo import create_demo_app


class TestDashboardDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_demo_app()
        cls.client = cls.app.test_client()

    def test_frontend_index(self):
        """Dashboard HTML loads successfully."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Monitoreo de Red ISP", response.data)

    def test_api_config(self):
        """Sanitized topology config does not leak credentials."""
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("routers", data)
        self.assertIn("netonix_switches", data)
        # Ensure password keys are absent
        for router in data["routers"]:
            self.assertNotIn("password", router)
            self.assertNotIn("user", router)
            self.assertIn("name", router)

    def test_api_state_with_demo_data(self):
        """State endpoint returns latest readings and last run status."""
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsNotNone(data["ts"])
        self.assertTrue(len(data["readings"]) > 0)
        # Verify Router-Core readings are present
        entities = {r["entity"] for r in data["readings"]}
        self.assertIn("Router-Core", entities)
        self.assertIn("AirControl-Tower1", entities)

    def test_api_history(self):
        """History endpoint returns time-series data for a specific entity & metric."""
        response = self.client.get("/api/history?entity=Router-Core&metric=cpu_percent&hours=6")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(isinstance(data, list))
        self.assertTrue(len(data) > 0)
        self.assertIn("ts", data[0])
        self.assertIn("value", data[0])


if __name__ == "__main__":
    unittest.main()
