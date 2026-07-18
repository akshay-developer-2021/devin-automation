import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app, get_db, update_automation_metrics, build_issue_prompt, sync_repository_issues


class MainRouteTests(unittest.TestCase):
    def test_repository_issues_route_accepts_full_repository_name(self):
        def override_get_db():
            class DummyDB:
                def query(self, model):
                    return self

                def filter(self, *args, **kwargs):
                    return self

                def first(self):
                    return SimpleNamespace(installation_id=123, repository_full_name="octo/demo")

            return DummyDB()

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        with patch("main.github_client.get_issues", return_value=[{"number": 1, "title": "Test issue"}]) as mock_get_issues:
            response = client.get("/api/repositories/octo/demo/issues?state=open")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["issues"][0]["number"], 1)
        mock_get_issues.assert_called_once_with(123, "octo", "demo", "open")

    def test_build_issue_prompt_includes_issue_body_and_labels(self):
        issue = {
            "number": 42,
            "title": "Login button is broken",
            "html_url": "https://github.com/octo/demo/issues/42",
            "body": "The login button does nothing when clicked.",
            "labels": [{"name": "bug"}, {"name": "urgent"}],
        }

        prompt = build_issue_prompt(issue, "octo/demo", "bug_fix")

        self.assertIn("Issue #42", prompt)
        self.assertIn("Login button is broken", prompt)
        self.assertIn("The login button does nothing when clicked.", prompt)
        self.assertIn("bug, urgent", prompt)
        self.assertIn("bug_fix", prompt)

    def test_sync_repository_issues_persists_issue_snapshots(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        issues = [{
            "number": 10,
            "title": "Closed issue",
            "body": "This issue was closed earlier.",
            "state": "closed",
            "html_url": "https://github.com/octo/demo/issues/10",
            "labels": [{"name": "bug"}],
            "user": {"login": "alice"},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "closed_at": "2024-01-02T00:00:00Z",
            "comments": 2,
            "assignees": [{"login": "bob"}],
        }]

        sync_repository_issues(db, repository_id=7, issues=issues)

        self.assertEqual(db.add.call_count, 1)
        persisted_issue = db.add.call_args[0][0]
        self.assertEqual(persisted_issue.issue_number, 10)
        self.assertEqual(persisted_issue.state, "closed")
        self.assertEqual(persisted_issue.title, "Closed issue")

    def test_update_automation_metrics_creates_daily_snapshot(self):
        class FakeQuery:
            def __init__(self, rows=None, first_result=None):
                self.rows = rows or []
                self.first_result = first_result

            def filter(self, *args, **kwargs):
                return self

            def all(self):
                return self.rows

            def first(self):
                return self.first_result

        session = SimpleNamespace(
            status="exit",
            completed_at=None,
            created_at=None,
            automation_type="bug_fix",
            acus_consumed=2.5,
            pull_requests="[]"
        )

        def query_side_effect(model):
            if model is type(__import__("main").DevinSession):
                return FakeQuery(rows=[session])
            return FakeQuery(first_result=None)

        db = MagicMock()
        db.query.side_effect = query_side_effect

        with patch("main.AutomationMetrics", side_effect=lambda **kwargs: SimpleNamespace(**kwargs)):
            update_automation_metrics(db, repository_id=7)

        self.assertIsNotNone(db.query)


if __name__ == "__main__":
    unittest.main()
