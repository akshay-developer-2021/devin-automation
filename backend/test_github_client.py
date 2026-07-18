import unittest
from unittest.mock import Mock, patch

from github_client import GitHubClient


class GitHubClientTests(unittest.TestCase):
    def test_get_repositories_for_installation_uses_installation_repositories_endpoint(self):
        client = GitHubClient.__new__(GitHubClient)
        client.get_installation_access_token = Mock(return_value="test-token")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "repositories": [
                {
                    "id": 1,
                    "name": "demo",
                    "full_name": "octo/demo",
                    "owner": {"login": "octo"},
                    "private": False,
                    "html_url": "https://github.com/octo/demo",
                    "description": None,
                    "language": "Python",
                    "updated_at": "2024-01-01T00:00:00Z",
                }
            ]
        }

        with patch("github_client.requests.get", return_value=mock_response) as mock_get:
            repos = client.get_repositories_for_installation(123)

        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0]["full_name"], "octo/demo")

        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], "https://api.github.com/installation/repositories")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")


if __name__ == "__main__":
    unittest.main()
