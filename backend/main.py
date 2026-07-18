from fastapi import FastAPI, HTTPException, Header, Request, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import asyncio
import threading
from dotenv import load_dotenv
import hmac
import hashlib
import json
from datetime import datetime, timedelta
import logging

from database import init_db, get_db, GitHubInstallation, MonitoredRepository, DevinSession, AutomationMetrics, PersistedIssue
from github_client import GitHubClient
from devin_client import DevinClient
from sqlalchemy.orm import Session

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

polling_thread: Optional[threading.Thread] = None
polling_stop_event = threading.Event()

async def refresh_active_sessions():
    db = next(get_db())
    try:
        # Only poll sessions that are actively running or starting
        # Suspended sessions are handled by completion logic and don't need polling
        active_sessions = db.query(DevinSession).filter(
            DevinSession.status.in_(["new", "claimed", "running", "resuming"]),
            DevinSession.completed_at.is_(None)
        ).all()

        logger.info(f"Found {len(active_sessions)} active sessions to refresh")
        for session in active_sessions:
            try:
                remote_session = await devin_client.get_session(session.session_id)
                if not remote_session:
                    continue

                parsed = devin_client.parse_session_result(remote_session)
                session.status = parsed["status"] or session.status
                session.status_detail = parsed.get("status_detail")
                session.acus_consumed = parsed["acus_consumed"]
                session.pull_requests = parsed["pull_requests"]
                session.structured_output = parsed["structured_output"]
                session.session_url = parsed.get("session_url")
                session.updated_at = datetime.utcnow()

                # Handle session completion based on official Devin lifecycle
                status = parsed["status"]
                status_detail = parsed.get("status_detail")

                logger.info(f"Session {session.session_id}: status={status}, status_detail={status_detail}, has_prs={bool(session.pull_requests)}")

                # Check if session has PRs - if so, terminate and mark as completed
                if session.pull_requests:
                    try:
                        prs = json.loads(session.pull_requests)
                        if prs and len(prs) > 0 and status not in ["exit", "error"]:
                            logger.info(f"Session {session.session_id} has PRs, terminating and marking as completed")
                            try:
                                await devin_client.terminate_session(session.session_id, archive=False)
                            except Exception as e:
                                logger.error(f"Failed to terminate session {session.session_id}: {e}")
                            session.status = "exit"
                            session.status_detail = "terminated_with_pr"
                            session.completed_at = datetime.utcnow()
                            db.commit()
                            logger.info(f"Session {session.session_id} terminated and marked as completed")
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse PRs for session {session.session_id}")

                # Session is complete if:
                # 1. Status is 'exit' (clean exit)
                # 2. Status is 'running' with status_detail 'finished' (task complete)
                elif status == "exit" or (status == "running" and status_detail == "finished"):
                    session.completed_at = datetime.utcnow()
                    logger.info(f"Session {session.session_id} completed successfully")

                # Handle problematic suspensions that shouldn't be retried
                elif status == "suspended" and status_detail in [
                    "out_of_credits", "out_of_quota", "no_quota_allocation",
                    "payment_declined", "org_usage_limit_exceeded",
                    "total_session_limit_exceeded"
                ]:
                    session.completed_at = datetime.utcnow()
                    session.status = "error"
                    session.error_message = f"Suspended due to {status_detail}"
                    logger.warning(f"Session {session.session_id} failed due to {status_detail}")

                db.commit()
            except Exception as e:
                logger.error(f"Failed to refresh Devin session {session.session_id}: {e}")
    finally:
        db.close()

def background_poller():
    """Background task to poll for active sessions (runs in thread)"""
    logger.info("Background poller thread started")
    while not polling_stop_event.is_set():
        try:
            logger.info("Calling refresh_active_sessions")
            asyncio.run(refresh_active_sessions())
            logger.info("refresh_active_sessions completed")
        except Exception as e:
            logger.error(f"Background poller failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        logger.info("Waiting 10 seconds before next poll")
        polling_stop_event.wait(10)
    logger.info("Background poller thread stopped")

def start_background_poller():
    """Start the background poller in a separate thread"""
    global polling_thread
    if polling_thread and polling_thread.is_alive():
        logger.info("Background poller already running")
        return
    
    polling_thread = threading.Thread(target=background_poller, daemon=True)
    polling_thread.start()
    logger.info("Background poller thread created")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    # Startup
    init_db()
    logger.info("Database initialized")
    start_background_poller()
    yield
    # Shutdown
    if polling_thread and polling_thread.is_alive():
        polling_stop_event.set()
        polling_thread.join(timeout=5)
        logger.info("Background poller stopped")

app = FastAPI(title="Devin Automation Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

# Initialize clients
github_client = GitHubClient()
devin_client = DevinClient()

# Pydantic models
class InstallationRequest(BaseModel):
    installation_id: int
    github_account_id: int
    github_account_login: str
    account_type: str

class RepositoryConfig(BaseModel):
    repository_id: int
    repository_full_name: str
    owner_login: str
    automation_enabled: bool = False
    automation_config: Optional[Dict[str, Any]] = None

class DevinSessionRequest(BaseModel):
    repository_full_name: str
    issue_number: int
    issue_title: Optional[str] = None
    automation_type: str = "general"

class AutomationSettings(BaseModel):
    enabled: bool
    trigger_labels: List[str] = ["automate:devin"]
    max_concurrent_sessions: int = 5
    automation_types: Dict[str, str] = {}


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def sync_repository_issues(db: Session, repository_id: int, issues: List[Dict[str, Any]]) -> None:
    """Persist issue snapshots locally so the UI can show historical and closed issues."""
    for issue in issues:
        existing = db.query(PersistedIssue).filter(
            PersistedIssue.repository_id == repository_id,
            PersistedIssue.issue_number == issue.get("number"),
        ).first()

        payload = {
            "title": issue.get("title"),
            "body": issue.get("body"),
            "state": issue.get("state", "open"),
            "html_url": issue.get("html_url"),
            "labels": json.dumps(issue.get("labels", [])),
            "user_login": (issue.get("user") or {}).get("login"),
            "created_at": _parse_datetime(issue.get("created_at")),
            "updated_at": _parse_datetime(issue.get("updated_at")),
            "closed_at": _parse_datetime(issue.get("closed_at")),
            "comments": issue.get("comments", 0),
            "assignees": json.dumps(issue.get("assignees", [])),
        }

        if existing:
            existing.title = payload["title"]
            existing.body = payload["body"]
            existing.state = payload["state"]
            existing.html_url = payload["html_url"]
            existing.labels = payload["labels"]
            existing.user_login = payload["user_login"]
            existing.created_at = payload["created_at"]
            existing.updated_at = payload["updated_at"]
            existing.closed_at = payload["closed_at"]
            existing.comments = payload["comments"]
            existing.assignees = payload["assignees"]
            existing.updated_at_db = datetime.utcnow()
        else:
            db.add(PersistedIssue(
                repository_id=repository_id,
                issue_number=issue.get("number"),
                **payload,
            ))

    db.commit()


def build_issue_prompt(issue: Dict[str, Any], repository_full_name: str, automation_type: str) -> str:
    """Build a richer Devin prompt from GitHub issue context."""
    title = issue.get("title") or "Untitled issue"
    body = (issue.get("body") or "").strip() or "No description provided."
    labels = ", ".join([label.get("name", "") for label in issue.get("labels", []) if label.get("name")]) or "none"
    issue_url = issue.get("html_url") or ""
    issue_number = issue.get("number")

    return f"""You are working on a GitHub issue for repository {repository_full_name}.

Issue #{issue_number}: {title}
URL: {issue_url}
Labels: {labels}

Description:
{body}

Task:
- Review the issue carefully.
- Implement the most appropriate fix or change.
- Keep the solution aligned with the repository's existing patterns.
- If a pull request is needed, include a clear summary and testing notes.
- Use the automation type '{automation_type}' as the guiding context.

IMPORTANT: Once you have completed the task (either by fixing the issue or creating a pull request), you MUST explicitly exit the session. Do not leave the session suspended or running. Type 'exit' to terminate the session when your work is complete.
"""

@app.get("/")
async def root():
    return {"message": "Devin Automation Backend API", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.get("/install")
async def install_redirect():
    """Get GitHub App installation URL (GitHub Apps don't redirect like OAuth)"""
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    
    # GitHub App installation URL - no redirect, webhook handles installation
    install_url = f"https://github.com/apps/{os.getenv('GITHUB_APP_NAME', 'devin-issue-resolver')}/installations/new"
    
    return {
        "install_url": install_url,
        "note": "GitHub Apps use webhooks for installation confirmation, not redirects",
        "redirect_url": f"{frontend_url}/settings"
    }

@app.post("/api/installations")
async def register_installation(request: InstallationRequest, db: Session = Depends(get_db)):
    """Register a GitHub App installation"""
    try:
        # Check if installation already exists
        existing = db.query(GitHubInstallation).filter(
            GitHubInstallation.installation_id == request.installation_id
        ).first()
        
        if existing:
            # Update existing installation
            existing.github_account_id = request.github_account_id
            existing.github_account_login = request.github_account_login
            existing.account_type = request.account_type
            existing.updated_at = datetime.utcnow()
        else:
            # Create new installation
            installation = GitHubInstallation(
                installation_id=request.installation_id,
                github_account_id=request.github_account_id,
                github_account_login=request.github_account_login,
                account_type=request.account_type
            )
            db.add(installation)
        
        db.commit()
        logger.info(f"Registered installation {request.installation_id}")
        
        # Automatically sync repositories after installation
        try:
            repos = github_client.get_repositories_for_installation(request.installation_id)
            synced_count = 0
            for repo in repos:
                existing = db.query(MonitoredRepository).filter(
                    MonitoredRepository.repository_full_name == repo["full_name"]
                ).first()
                
                if existing:
                    existing.repository_id = repo["id"]
                    existing.repository_name = repo["name"]
                    existing.owner_login = repo["owner_login"]
                    existing.updated_at = datetime.utcnow()
                else:
                    repository = MonitoredRepository(
                        installation_id=request.installation_id,
                        repository_id=repo["id"],
                        repository_name=repo["name"],
                        repository_full_name=repo["full_name"],
                        owner_login=repo["owner_login"]
                    )
                    db.add(repository)
                
                synced_count += 1
            
            db.commit()
            logger.info(f"Auto-synced {synced_count} repositories for installation {request.installation_id}")
        except Exception as sync_error:
            logger.error(f"Failed to auto-sync repositories: {sync_error}")
            # Don't fail the installation if sync fails
        
        return {"status": "success", "installation_id": request.installation_id}
    except Exception as e:
        logger.error(f"Failed to register installation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/installations")
async def get_installations(db: Session = Depends(get_db)):
    """Get all GitHub App installations"""
    try:
        installations = db.query(GitHubInstallation).all()
        return {
            "installations": [
                {
                    "id": inst.installation_id,
                    "github_account_login": inst.github_account_login,
                    "account_type": inst.account_type,
                    "created_at": inst.created_at.isoformat()
                }
                for inst in installations
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get installations: {e}")
        # Return empty list instead of error to handle fresh DB gracefully
        return {"installations": []}

@app.post("/api/repositories/sync")
async def sync_repositories(installation_id: int, db: Session = Depends(get_db)):
    """Sync repositories from GitHub for an installation"""
    try:
        # Ensure installation exists in database
        installation = db.query(GitHubInstallation).filter(
            GitHubInstallation.installation_id == installation_id
        ).first()
        
        if not installation:
            raise HTTPException(status_code=404, detail="Installation not found. Please install the GitHub App first.")
        
        # Get repositories from GitHub
        repos = github_client.get_repositories_for_installation(installation_id)
        
        synced_count = 0
        for repo in repos:
            # Check if repository already exists
            existing = db.query(MonitoredRepository).filter(
                MonitoredRepository.repository_full_name == repo["full_name"]
            ).first()
            
            if existing:
                # Update existing repository
                existing.repository_id = repo["id"]
                existing.repository_name = repo["name"]
                existing.owner_login = repo["owner_login"]
                existing.updated_at = datetime.utcnow()
            else:
                # Create new repository
                repository = MonitoredRepository(
                    installation_id=installation_id,
                    repository_id=repo["id"],
                    repository_name=repo["name"],
                    repository_full_name=repo["full_name"],
                    owner_login=repo["owner_login"]
                )
                db.add(repository)
            
            synced_count += 1
        
        db.commit()
        logger.info(f"Synced {synced_count} repositories for installation {installation_id}")
        return {"status": "success", "synced_count": synced_count}
    except Exception as e:
        logger.error(f"Failed to sync repositories: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/repositories")
async def get_repositories(db: Session = Depends(get_db)):
    """Get all monitored repositories"""
    try:
        repositories = db.query(MonitoredRepository).filter(
            MonitoredRepository.is_active == True
        ).all()
        
        def _get_trigger_labels(repo: MonitoredRepository) -> List[str]:
            if not repo.automation_config:
                return ["automate:devin"]
            try:
                config = json.loads(repo.automation_config)
                labels = config.get("trigger_labels")
                if isinstance(labels, list) and labels:
                    return labels
            except (TypeError, ValueError):
                logger.warning(f"Invalid automation config for repository {repo.id}: {repo.automation_config}")
            return ["automate:devin"]

        return {
            "repositories": [
                {
                    "id": repo.id,
                    "repository_full_name": repo.repository_full_name,
                    "owner_login": repo.owner_login,
                    "automation_enabled": repo.automation_enabled,
                    "trigger_labels": _get_trigger_labels(repo),
                    "created_at": repo.created_at.isoformat()
                }
                for repo in repositories
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get repositories: {e}")
        # Return empty list instead of error to handle fresh DB gracefully
        return {"repositories": []}

@app.put("/api/repositories/{repository_id}/config")
async def update_repository_config(
    repository_id: int,
    config: RepositoryConfig,
    db: Session = Depends(get_db)
):
    """Update repository configuration"""
    try:
        repository = db.query(MonitoredRepository).filter(
            MonitoredRepository.id == repository_id
        ).first()
        
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        repository.automation_enabled = config.automation_enabled
        if config.automation_config:
            repository.automation_config = json.dumps(config.automation_config)
        repository.updated_at = datetime.utcnow()
        
        db.commit()
        logger.info(f"Updated config for repository {repository_id}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to update repository config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/repositories/{repository_full_name:path}/issues")
async def get_repository_issues(repository_full_name: str, state: str = "all", db: Session = Depends(get_db)):
    """Get issues from a repository (open and closed)"""
    try:
        if "/" not in repository_full_name:
            raise HTTPException(status_code=400, detail="Repository must be in owner/repo format")

        owner, repo_name = repository_full_name.split("/", 1)
        repository = db.query(MonitoredRepository).filter(
            MonitoredRepository.repository_full_name == repository_full_name
        ).first()

        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Fetch both open and closed issues
        issues = github_client.get_issues(
            repository.installation_id,
            owner,
            repo_name,
            "all"
        )

        repository_id = getattr(repository, "id", None)
        if repository_id is not None:
            sync_repository_issues(db, repository_id, issues)
            persisted_issues = db.query(PersistedIssue).filter(
                PersistedIssue.repository_id == repository_id
            ).order_by(PersistedIssue.updated_at_db.desc()).all()

            # Get all issue numbers that have Devin sessions
            session_issue_numbers = set()
            sessions = db.query(DevinSession).filter(
                DevinSession.repository_id == repository_id
            ).all()
            for session in sessions:
                if session.issue_number:
                    session_issue_numbers.add(session.issue_number)

            # Filter issues: show open issues OR closed issues with sessions
            filtered_issues = []
            for issue in persisted_issues:
                # Always show open issues
                if issue.state == "open":
                    filtered_issues.append(issue)
                # Show closed issues only if they have a session
                elif issue.state == "closed" and issue.issue_number in session_issue_numbers:
                    filtered_issues.append(issue)

            issue_payload = []
            for issue in filtered_issues:
                issue_payload.append({
                    "id": issue.id,
                    "number": issue.issue_number,
                    "title": issue.title,
                    "body": issue.body,
                    "state": issue.state,
                    "html_url": issue.html_url,
                    "labels": json.loads(issue.labels) if issue.labels else [],
                    "user": {"login": issue.user_login},
                    "created_at": issue.created_at.isoformat() if issue.created_at else None,
                    "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
                    "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
                    "comments": issue.comments,
                    "assignees": json.loads(issue.assignees) if issue.assignees else [],
                })

            return {"issues": issue_payload}

        return {"issues": issues}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get issues: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/devin/session")
async def start_devin_session(
    request: DevinSessionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Start a Devin session for a specific issue"""
    try:
        # Get repository
        repository = db.query(MonitoredRepository).filter(
            MonitoredRepository.repository_full_name == request.repository_full_name
        ).first()
        
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        # Get issue details
        owner, repo_name = request.repository_full_name.split("/")
        issues = github_client.get_issues(
            repository.installation_id,
            owner,
            repo_name,
            "open"
        )
        
        issue = next((i for i in issues if i["number"] == request.issue_number), None)
        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")
        
        prompt = build_issue_prompt(issue, request.repository_full_name, request.automation_type)

        # Create Devin session
        try:
            session_data = await devin_client.create_session(
                prompt=prompt,
                repository=request.repository_full_name,
                issue_number=request.issue_number,
                automation_type=request.automation_type
            )
        except Exception as e:
            logger.error(f"Devin session creation failed: {e}")
            devin_session = DevinSession(
                session_id=f"local-fallback-{request.issue_number}",
                org_id=os.getenv("DEVIN_ORG_ID"),
                repository_id=repository.id,
                prompt=prompt,
                status="error",
                issue_number=request.issue_number,
                issue_title=request.issue_title or issue["title"],
                automation_type=request.automation_type,
                trigger_type="manual",
                error_message=str(e)
            )
            db.add(devin_session)
            db.commit()
            return {
                "status": "queued",
                "message": "Devin session could not be started right now",
                "error": str(e)
            }

        # Store session in database
        devin_session = DevinSession(
            session_id=session_data["session_id"],
            org_id=os.getenv("DEVIN_ORG_ID"),
            repository_id=repository.id,
            prompt=prompt,
            status="new",
            issue_number=request.issue_number,
            issue_title=request.issue_title or issue["title"],
            automation_type=request.automation_type,
            trigger_type="manual"
        )
        db.add(devin_session)
        db.commit()
        
        # Start background task to monitor session
        background_tasks.add_task(
            monitor_devin_session,
            devin_session.id,
            session_data["session_id"],
            repository.installation_id,
            request.repository_full_name,
            request.issue_number
        )
        
        logger.info(f"Started Devin session {session_data['session_id']} for issue {request.issue_number}")
        return {
            "status": "success",
            "session_id": session_data["session_id"],
            "session_url": session_data.get("url")
        }
    except Exception as e:
        logger.error(f"Failed to start Devin session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def update_automation_metrics(db: Session, repository_id: Optional[int] = None):
    """Create/update a daily automation metrics snapshot from Devin sessions."""
    try:
        session_query = db.query(DevinSession)
        if repository_id is not None:
            session_query = session_query.filter(DevinSession.repository_id == repository_id)

        sessions = session_query.all()
        if not sessions:
            return

        today = datetime.utcnow().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = start_of_day + timedelta(days=1)

        existing_query = db.query(AutomationMetrics)
        if repository_id is not None:
            existing_query = existing_query.filter(AutomationMetrics.repository_id == repository_id)

        existing = existing_query.filter(
            AutomationMetrics.date >= start_of_day,
            AutomationMetrics.date < end_of_day
        ).first()

        if existing is None:
            metric = AutomationMetrics(
                date=datetime.combine(today, datetime.min.time()),
                repository_id=repository_id,
                total_sessions=0,
                successful_sessions=0,
                failed_sessions=0,
                avg_completion_time=None,
                total_acus_consumed=0.0,
                prs_created=0,
                automation_type="all"
            )
            db.add(metric)
            db.commit()
            db.refresh(metric)
            existing = metric

        successful_sessions = sum(1 for session in sessions if session.status == "exit")
        failed_sessions = sum(1 for session in sessions if session.status == "error")
        total_acus = sum(session.acus_consumed or 0.0 for session in sessions)
        prs_created = sum(1 for session in sessions if session.pull_requests)
        completion_times = [
            (session.completed_at - session.created_at).total_seconds()
            for session in sessions
            if session.completed_at and session.created_at
        ]

        existing.total_sessions = len(sessions)
        existing.successful_sessions = successful_sessions
        existing.failed_sessions = failed_sessions
        existing.avg_completion_time = sum(completion_times) / len(completion_times) if completion_times else None
        existing.total_acus_consumed = total_acus
        existing.prs_created = prs_created
        db.commit()
    except Exception as e:
        logger.error(f"Failed to update automation metrics: {e}")

async def monitor_devin_session(
    db_session_id: int,
    devin_session_id: str,
    installation_id: int,
    repository_full_name: str,
    issue_number: int
):
    """Background task to monitor Devin session progress"""
    db = next(get_db())
    try:
        # Wait for session completion
        session = await devin_client.wait_for_completion(devin_session_id, timeout=3600)
        
        # Update database
        devin_session = db.query(DevinSession).filter(
            DevinSession.id == db_session_id
        ).first()
        
        if devin_session:
            parsed = devin_client.parse_session_result(session)
            devin_session.status = parsed["status"]
            devin_session.status_detail = parsed.get("status_detail")
            devin_session.acus_consumed = parsed["acus_consumed"]
            devin_session.pull_requests = parsed["pull_requests"]
            devin_session.structured_output = parsed["structured_output"]
            devin_session.session_url = parsed.get("session_url")
            devin_session.completed_at = datetime.utcnow()
            
            # Check if PRs were created
            prs = devin_client.get_pull_requests_from_session(session)

            if prs:
                # Terminate the session if it's still running and has PRs
                if parsed["status"] in ["running", "claimed", "new"]:
                    logger.info(f"Terminating session {devin_session_id} as PRs were created")
                    try:
                        await devin_client.terminate_session(devin_session_id, archive=False)
                        devin_session.status = "exit"
                        devin_session.status_detail = "terminated_with_pr"
                    except Exception as e:
                        logger.error(f"Failed to terminate session {devin_session_id}: {e}")

                # Comment on GitHub issue
                comment = f"✅ Devin completed successfully!\n\nPull Request(s) created:\n" + \
                          "\n".join([f"- {pr.get('pr_url')}" for pr in prs])
                owner, repo_name = repository_full_name.split("/")
                github_client.create_issue_comment(
                    installation_id,
                    owner,
                    repo_name,
                    issue_number,
                    comment
                )
            elif devin_client.is_session_successful(session):
                devin_session.error_message = "Session completed without PRs"
                # Comment on GitHub issue
                owner, repo_name = repository_full_name.split("/")
                github_client.create_issue_comment(
                    installation_id,
                    owner,
                    repo_name,
                    issue_number,
                    "ℹ️ Devin session completed but no PRs were created."
                )
            else:
                devin_session.error_message = "Session completed without success"
                # Comment on GitHub issue
                owner, repo_name = repository_full_name.split("/")
                github_client.create_issue_comment(
                    installation_id,
                    owner,
                    repo_name,
                    issue_number,
                    "❌ Devin session failed. Please check the logs for details."
                )
            
            db.commit()
            update_automation_metrics(db, repository_id=devin_session.repository_id)
            logger.info(f"Session {devin_session_id} monitoring completed")
    except Exception as e:
        logger.error(f"Error monitoring session {devin_session_id}: {e}")
        # Update session with error
        devin_session = db.query(DevinSession).filter(
            DevinSession.id == db_session_id
        ).first()
        if devin_session:
            devin_session.status = "error"
            devin_session.error_message = str(e)
            devin_session.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()

@app.get("/api/sessions")
async def get_sessions(repository_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Get Devin sessions"""
    try:
        query = db.query(DevinSession)
        if repository_id:
            query = query.filter(DevinSession.repository_id == repository_id)
        
        sessions = query.order_by(DevinSession.created_at.desc()).limit(50).all()
        
        return {
            "sessions": [
                {
                    "id": session.id,
                    "session_id": session.session_id,
                    "status": session.status,
                    "issue_number": session.issue_number,
                    "issue_title": session.issue_title,
                    "automation_type": session.automation_type,
                    "created_at": session.created_at.isoformat(),
                    "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                    "acus_consumed": session.acus_consumed,
                    "pull_requests": json.loads(session.pull_requests) if session.pull_requests else [],
                    "session_url": session.session_url,
                    "repository_full_name": session.repository.repository_full_name if session.repository else None
                }
                for session in sessions
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get sessions: {e}")
        # Return empty list instead of error to handle fresh DB gracefully
        return {"sessions": []}

@app.get("/api/metrics")
async def get_metrics(repository_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Get automation metrics"""
    try:
        query = db.query(AutomationMetrics).join(MonitoredRepository)
        if repository_id:
            query = query.filter(AutomationMetrics.repository_id == repository_id)

        metrics = query.order_by(AutomationMetrics.date.desc()).limit(30).all()
        metrics = sorted(metrics, key=lambda metric: metric.date)

        return {
            "metrics": [
                {
                    "date": metric.date.isoformat(),
                    "total_sessions": metric.total_sessions,
                    "successful_sessions": metric.successful_sessions,
                    "failed_sessions": metric.failed_sessions,
                    "avg_completion_time": metric.avg_completion_time,
                    "total_acus_consumed": metric.total_acus_consumed,
                    "prs_created": metric.prs_created,
                    "automation_type": metric.automation_type,
                    "repository_full_name": metric.repository.repository_full_name if metric.repository else None
                }
                for metric in metrics
            ]
        }
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        # Return empty list instead of error to handle fresh DB gracefully
        return {"metrics": []}

@app.post("/webhooks/github")
async def github_webhook(request: Request, x_hub_signature: str = Header(None), background_tasks: BackgroundTasks = None):
    """Handle GitHub webhooks forwarded through Smee or other proxies."""
    body = await request.body()
    event_type = request.headers.get("X-GitHub-Event", "unknown")
    logger.info(f"Received webhook: {event_type} from {request.headers.get('x-forwarded-for', 'unknown')}")

    if GITHUB_WEBHOOK_SECRET:
        expected_signature = "sha1=" + hmac.new(
            GITHUB_WEBHOOK_SECRET.encode(),
            body,
            hashlib.sha1
        ).hexdigest()

        if x_hub_signature and not hmac.compare_digest(expected_signature, x_hub_signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Handle different event types
    if event_type == "installation":
        await handle_installation_event(payload)
    elif event_type == "issues":
        await handle_issues_event(payload, background_tasks)
    else:
        logger.info(f"Ignoring unsupported webhook event: {event_type}")

    return {"status": "received"}

async def handle_installation_event(payload: Dict[str, Any]):
    """Handle installation events"""
    action = payload.get("action")
    installation = payload.get("installation", {})
    
    if action in ["created", "updated"]:
        # Sync installation to database
        db = next(get_db())
        try:
            existing = db.query(GitHubInstallation).filter(
                GitHubInstallation.installation_id == installation["id"]
            ).first()
            
            if existing:
                existing.github_account_id = installation["account"]["id"]
                existing.github_account_login = installation["account"]["login"]
                existing.account_type = installation["account"]["type"]
                existing.updated_at = datetime.utcnow()
            else:
                new_installation = GitHubInstallation(
                    installation_id=installation["id"],
                    github_account_id=installation["account"]["id"],
                    github_account_login=installation["account"]["login"],
                    account_type=installation["account"]["type"]
                )
                db.add(new_installation)
            
            db.commit()
            logger.info(f"Processed installation event: {action}")
            
            # Automatically sync repositories after installation
            try:
                repos = github_client.get_repositories_for_installation(installation["id"])
                synced_count = 0
                for repo in repos:
                    existing = db.query(MonitoredRepository).filter(
                        MonitoredRepository.repository_full_name == repo["full_name"]
                    ).first()
                    
                    if existing:
                        existing.repository_id = repo["id"]
                        existing.repository_name = repo["name"]
                        existing.owner_login = repo["owner_login"]
                        existing.updated_at = datetime.utcnow()
                    else:
                        repository = MonitoredRepository(
                            installation_id=installation["id"],
                            repository_id=repo["id"],
                            repository_name=repo["name"],
                            repository_full_name=repo["full_name"],
                            owner_login=repo["owner_login"]
                        )
                        db.add(repository)
                    
                    synced_count += 1
                
                db.commit()
                logger.info(f"Auto-synced {synced_count} repositories from installation webhook")
            except Exception as sync_error:
                logger.error(f"Failed to auto-sync repositories from webhook: {sync_error}")
                # Don't fail the installation if sync fails
        finally:
            db.close()

async def handle_issues_event(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    """Handle issues events"""
    action = payload.get("action")
    issue = payload.get("issue", {})
    repository = payload.get("repository", {})
    
    # Only handle newly opened issues with automation labels
    if action == "opened":
        labels = [label["name"] for label in issue.get("labels", [])]
        
        # Check if issue has automation trigger labels
        db = next(get_db())
        try:
            repo = db.query(MonitoredRepository).filter(
                MonitoredRepository.repository_full_name == repository["full_name"]
            ).first()
            
            if repo and repo.automation_enabled:
                automation_config = json.loads(repo.automation_config) if repo.automation_config else {}
                trigger_labels = automation_config.get("trigger_labels", ["automate:devin"])
                
                if any(label in labels for label in trigger_labels):
                    # Determine automation type from labels
                    automation_type = "general"
                    for label in labels:
                        if "dependency" in label.lower():
                            automation_type = "dependency_upgrade"
                        elif "vulnerability" in label.lower() or "security" in label.lower():
                            automation_type = "vulnerability_fix"
                        elif "bug" in label.lower():
                            automation_type = "bug_fix"
                    
                    # Start Devin session
                    session_request = DevinSessionRequest(
                        repository_full_name=repository["full_name"],
                        issue_number=issue["number"],
                        issue_title=issue["title"],
                        automation_type=automation_type
                    )
                    
                    try:
                        await start_devin_session(session_request, background_tasks, db)
                        logger.info(f"Auto-started Devin session for issue #{issue['number']}")
                    except Exception as e:
                        logger.error(f"Failed to auto-start Devin session for issue #{issue['number']}: {e}", exc_info=True)
        finally:
            db.close()
