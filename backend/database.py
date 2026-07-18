from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@postgres:5432/devin_automation")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class GitHubInstallation(Base):
    __tablename__ = "github_installations"
    
    id = Column(Integer, primary_key=True, index=True)
    installation_id = Column(Integer, unique=True, index=True)
    github_account_id = Column(Integer, index=True)
    github_account_login = Column(String)
    account_type = Column(String)  # User or Organization
    access_token = Column(Text)
    token_expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    repositories = relationship("MonitoredRepository", back_populates="installation")

class MonitoredRepository(Base):
    __tablename__ = "monitored_repositories"
    
    id = Column(Integer, primary_key=True, index=True)
    installation_id = Column(Integer, ForeignKey("github_installations.installation_id"))
    repository_id = Column(Integer, index=True)
    repository_name = Column(String, index=True)
    repository_full_name = Column(String, unique=True, index=True)
    owner_login = Column(String)
    is_active = Column(Boolean, default=True)
    automation_enabled = Column(Boolean, default=False)
    automation_config = Column(Text, nullable=True)  # JSON string for label triggers, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    installation = relationship("GitHubInstallation", back_populates="repositories")
    devin_sessions = relationship("DevinSession", back_populates="repository")
    persisted_issues = relationship("PersistedIssue", back_populates="repository")

class PersistedIssue(Base):
    __tablename__ = "persisted_issues"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("monitored_repositories.id"), index=True)
    issue_number = Column(Integer, index=True)
    title = Column(String, nullable=True)
    body = Column(Text, nullable=True)
    state = Column(String, default="open")
    html_url = Column(String, nullable=True)
    labels = Column(Text, nullable=True)  # JSON string
    user_login = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    comments = Column(Integer, default=0)
    assignees = Column(Text, nullable=True)  # JSON string
    created_at_db = Column(DateTime, default=datetime.utcnow)
    updated_at_db = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    repository = relationship("MonitoredRepository", back_populates="persisted_issues")

class DevinSession(Base):
    __tablename__ = "devin_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    org_id = Column(String, index=True)
    repository_id = Column(Integer, ForeignKey("monitored_repositories.id"))
    prompt = Column(Text)
    status = Column(String, index=True)  # new, claimed, running, exit, error, suspended, resuming
    status_detail = Column(String, nullable=True)
    issue_number = Column(Integer, nullable=True, index=True)
    issue_title = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    acus_consumed = Column(Float, default=0.0)
    pull_requests = Column(Text, nullable=True)  # JSON string
    structured_output = Column(Text, nullable=True)  # JSON string
    session_url = Column(String, nullable=True)  # Devin session URL for debugging
    error_message = Column(Text, nullable=True)
    automation_type = Column(String)  # dependency_upgrade, vulnerability_fix, code_quality, etc.
    trigger_type = Column(String)  # webhook, manual, scheduled
    
    repository = relationship("MonitoredRepository", back_populates="devin_sessions")

class AutomationMetrics(Base):
    __tablename__ = "automation_metrics"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, default=datetime.utcnow, index=True)
    repository_id = Column(Integer, ForeignKey("monitored_repositories.id"), nullable=True)
    total_sessions = Column(Integer, default=0)
    successful_sessions = Column(Integer, default=0)
    failed_sessions = Column(Integer, default=0)
    avg_completion_time = Column(Float, nullable=True)  # in seconds
    total_acus_consumed = Column(Float, default=0.0)
    prs_created = Column(Integer, default=0)
    automation_type = Column(String, index=True)

    repository = relationship("MonitoredRepository")

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
