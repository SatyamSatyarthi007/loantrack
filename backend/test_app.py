import os
import unittest
from backend.app import app


class BackendAppTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_healthz_db_independent(self):
        """Verify liveness probe returns 200 without DB."""
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("status"), "ok")

    def test_readyz_fails_gracefully_when_db_down(self):
        """Verify readiness probe returns 503 (not 500 crash) when DB is offline."""
        resp = self.client.get("/readyz")
        self.assertEqual(resp.status_code, 503)
        data = resp.get_json()
        self.assertEqual(data.get("status"), "unavailable")
        self.assertIn("error", data)

    def test_post_loans_validation_missing_borrower(self):
        """Verify POST /loans rejects missing borrower_name."""
        resp = self.client.post("/loans", json={"loan_amount": 50000})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("borrower_name", resp.get_json().get("error", ""))

    def test_post_loans_validation_invalid_amount(self):
        """Verify POST /loans rejects non-positive loan_amount."""
        resp = self.client.post(
            "/loans",
            json={"borrower_name": "Acme", "loan_amount": -1000},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("loan_amount", resp.get_json().get("error", ""))

    def test_pod_metadata_headers(self):
        """Verify responses include served_by and version."""
        resp = self.client.get("/loans")
        # DB may be offline, but response must include metadata
        data = resp.get_json()
        self.assertIn("served_by", data)
        self.assertIn("version", data)


if __name__ == "__main__":
    unittest.main()
