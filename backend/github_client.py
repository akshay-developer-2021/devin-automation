from github import Github, GithubIntegration
import os
import jwt
import time
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from typing import List, Dict, Any, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GitHubClient:
    def __init__(self):
        self.app_id = os.getenv("GITHUB_APP_ID")
        self.private_key = os.getenv("GITHUB_PRIVATE_KEY")
        self.webhook_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
        
        if not all([self.app_id, self.private_key]):
            raise ValueError("GITHUB_APP_ID and GITHUB_PRIVATE_KEY must be set")
        
        # Initialize GitHub App with old-style GithubIntegration
        self.integration = GithubIntegration(
            self.app_id,
            self.private_key
        )
    
    def generate_jwt(self) -> str:
        """Generate JWT for GitHub App authentication"""
        private_key = serialization.load_pem_private_key(
            self.private_key.encode(),
            password=None,
            backend=default_backend()
        )
        
        payload = {
            "iat": int(time.time()) - 60,
            "exp": int(time.time()) + (10 * 60),
            "iss": self.app_id
        }
        
        token = jwt.encode(payload, private_key, algorithm="RS256")
        return token
    
    def get_installation_access_token(self, installation_id: int) -> str:
        """Get installation access token for a specific installation"""
        try:
            token = self.integration.get_access_token(installation_id)
            return token.token
        except Exception as e:
            logger.error(f"Failed to get installation token: {e}")
            raise
    
    def get_github_client_for_installation(self, installation_id: int) -> Github:
        """Get authenticated GitHub client for an installation"""
        try:
            token = self.get_installation_access_token(installation_id)
            return Github(token)
        except Exception as e:
            logger.error(f"Failed to create GitHub client: {e}")
            raise
    
    def get_installations(self) -> List[Dict[str, Any]]:
        """Get all installations of the GitHub App"""
        try:
            # Use integration object directly to get installations
            installations = self.integration.get_installations()
            
            result = []
            for installation in installations:
                result.append({
                    "id": installation.id,
                    "account_id": getattr(installation, 'account_id', None),
                    "account_login": getattr(installation, 'account_login', None),
                    "account_type": getattr(installation, 'account_type', None),
                    "account_url": getattr(installation, 'account_url', None)
                })
            
            return result
        except Exception as e:
            logger.error(f"Failed to get installations: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def get_repositories_for_installation(self, installation_id: int) -> List[Dict[str, Any]]:
        """Get repositories accessible to an installation"""
        try:
            # Get installation access token
            token = self.get_installation_access_token(installation_id)

            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            response = requests.get(
                "https://api.github.com/installation/repositories",
                headers=headers,
                params={"per_page": 100},
                timeout=30,
            )

            if response.status_code != 200:
                logger.error(f"Failed to get repositories: {response.status_code} - {response.text}")
                raise Exception(f"GitHub API error: {response.status_code} - {response.text}")

            data = response.json()

            result = []
            for repo in data.get("repositories", []):
                result.append({
                    "id": repo["id"],
                    "name": repo["name"],
                    "full_name": repo["full_name"],
                    "owner_login": repo["owner"]["login"],
                    "private": repo["private"],
                    "html_url": repo["html_url"],
                    "description": repo.get("description"),
                    "language": repo.get("language"),
                    "updated_at": repo.get("updated_at"),
                })

            return result
        except Exception as e:
            logger.error(f"Failed to get repositories: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def get_issues(self, installation_id: int, repo_owner: str, repo_name: str, state: str = "open") -> List[Dict[str, Any]]:
        """Get issues from a repository"""
        try:
            token = self.get_installation_access_token(installation_id)
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues"
            response = requests.get(url, headers=headers, params={"state": state, "per_page": 100}, timeout=30)

            if response.status_code != 200:
                logger.error(f"Failed to get issues: {response.status_code} - {response.text}")
                raise Exception(f"GitHub API error: {response.status_code} - {response.text}")

            data = response.json()

            result = []
            for issue in data:
                if issue.get("pull_request"):
                    continue

                labels = [{"name": label.get("name"), "color": label.get("color")} for label in issue.get("labels", [])]

                result.append({
                    "id": issue["id"],
                    "number": issue["number"],
                    "title": issue["title"],
                    "body": issue.get("body"),
                    "state": issue["state"],
                    "html_url": issue["html_url"],
                    "user": {
                        "login": issue.get("user", {}).get("login"),
                        "avatar_url": issue.get("user", {}).get("avatar_url"),
                    },
                    "labels": labels,
                    "created_at": issue.get("created_at"),
                    "updated_at": issue.get("updated_at"),
                    "closed_at": issue.get("closed_at"),
                    "comments": issue.get("comments", 0),
                    "assignees": [assignee.get("login") for assignee in issue.get("assignees", []) if assignee.get("login")],
                })

            return result
        except Exception as e:
            logger.error(f"Failed to get issues: {e}")
            raise
    
    def create_issue_comment(self, installation_id: int, repo_owner: str, repo_name: str, issue_number: int, body: str):
        """Create a comment on an issue"""
        try:
            github = self.get_github_client_for_installation(installation_id)
            repo = github.get_repo(f"{repo_owner}/{repo_name}")
            issue = repo.get_issue(issue_number)
            issue.create_comment(body)
            logger.info(f"Created comment on issue #{issue_number}")
        except Exception as e:
            logger.error(f"Failed to create comment: {e}")
            raise
    
    def update_issue_labels(self, installation_id: int, repo_owner: str, repo_name: str, issue_number: int, labels: List[str]):
        """Update labels on an issue"""
        try:
            github = self.get_github_client_for_installation(installation_id)
            repo = github.get_repo(f"{repo_owner}/{repo_name}")
            issue = repo.get_issue(issue_number)
            issue.set_labels(*labels)
            logger.info(f"Updated labels on issue #{issue_number}")
        except Exception as e:
            logger.error(f"Failed to update labels: {e}")
            raise
    
    def get_pull_requests(self, installation_id: int, repo_owner: str, repo_name: str, state: str = "open") -> List[Dict[str, Any]]:
        """Get pull requests from a repository"""
        try:
            github = self.get_github_client_for_installation(installation_id)
            repo = github.get_repo(f"{repo_owner}/{repo_name}")
            pull_requests = repo.get_pulls(state=state)
            
            result = []
            for pr in pull_requests:
                result.append({
                    "id": pr.id,
                    "number": pr.number,
                    "title": pr.title,
                    "state": pr.state,
                    "html_url": pr.html_url,
                    "user": {
                        "login": pr.user.login,
                        "avatar_url": pr.user.avatar_url
                    },
                    "created_at": pr.created_at.isoformat() if pr.created_at else None,
                    "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
                    "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
                    "additions": pr.additions,
                    "deletions": pr.deletions,
                    "commits": pr.commits,
                    "review_comments": pr.review_comments
                })
            
            return result
        except Exception as e:
            logger.error(f"Failed to get pull requests: {e}")
            raise
    
    def create_pull_request(self, installation_id: int, repo_owner: str, repo_name: str, title: str, body: str, head: str, base: str = "main") -> Dict[str, Any]:
        """Create a pull request"""
        try:
            github = self.get_github_client_for_installation(installation_id)
            repo = github.get_repo(f"{repo_owner}/{repo_name}")
            pr = repo.create_pull(title=title, body=body, head=head, base=base)
            
            logger.info(f"Created PR #{pr.number}")
            return {
                "id": pr.id,
                "number": pr.number,
                "title": pr.title,
                "html_url": pr.html_url,
                "state": pr.state
            }
        except Exception as e:
            logger.error(f"Failed to create pull request: {e}")
            raise
