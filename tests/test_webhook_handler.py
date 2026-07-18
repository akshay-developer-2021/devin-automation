import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import main


class DummySession:
    def __init__(self, repo):
        self.repo = repo

    def query(self, model):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.repo

    def close(self):
        return None


class WebhookHandlerTests(unittest.TestCase):
    def test_handle_issues_event_does_not_raise_when_session_start_fails(self):
        repo = MagicMock()
        repo.automation_enabled = True
        repo.automation_config = '{"trigger_labels": ["automate:devin"]}'

        payload = {
            "action": "opened",
            "issue": {
                "number": 42,
                "title": "Issue title",
                "labels": [{"name": "automate:devin"}],
            },
            "repository": {"full_name": "owner/repo"},
        }

        with patch("main.get_db", return_value=iter([DummySession(repo)])):
            with patch("main.start_devin_session", new=AsyncMock(side_effect=HTTPException(status_code=404, detail="Repository not found"))):
                with patch("main.logger") as mock_logger:
                    asyncio.run(main.handle_issues_event(payload, background_tasks=MagicMock()))

        mock_logger.error.assert_called_once()
        self.assertIn("Failed to auto-start Devin session", mock_logger.error.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
