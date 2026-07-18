# Devin Automation - Event-Driven GitHub Issue Resolution

A full-stack application that automates GitHub issue resolution using Devin AI with event-driven triggers, real-time observability, and comprehensive analytics.

## Quick Start

1. **Clone and configure**
   ```bash
   git clone <your-repo>
   cd devin
   cp .env.example .env
   # Edit .env with your credentials
   ```

2. **Get credentials**
   - GitHub App: https://github.com/settings/apps
   - Devin API: https://app.devin.ai/settings/api-keys
   - Smee URL: https://smee.io (for local webhooks)

3. **Run with Docker**
   ```bash
   docker-compose up --build
   ```
   - Frontend: http://localhost:5173
   - Backend: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## Setup

### 1. Create GitHub App
- Go to https://github.com/settings/apps → New GitHub App
- Homepage: `http://localhost:5173`
- Setup URL: `http://localhost:5173` → redirect user back to our app
- Webhook URL: Your Smee URL
- Permissions: Issues (R/W), Repository contents (R/W), Pull requests (R/W), Metadata (R)
- Download the private key (.pem file)

### 2. Configure Environment
Edit `.env` with your values:
```env
GITHUB_APP_ID=your_app_id
GITHUB_APP_NAME=your_app_name
GITHUB_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----
your_private_key_content
-----END RSA PRIVATE KEY-----
GITHUB_WEBHOOK_SECRET=your_webhook_secret
SMEE_URL=https://smee.io/your-channel
DEVIN_API_KEY=your_devin_api_key
DEVIN_ORG_ID=your_devin_org_id
```

### 3. Install GitHub App
- Go to your GitHub App settings → Install App
- Select your repositories (e.g., your Apache Superset fork)

### 4. Configure in UI
1. Open http://localhost:5173
2. Go to Settings → Sync Repositories
3. Enable automation for your repository
4. Set trigger labels (default: `automate:devin`)

## Usage

### Manual Automation
1. Select repository from dropdown
2. View issues in Kanban board
3. Click "Start Devin" on any issue
4. Monitor progress in real-time

### Webhook Automation
1. Create GitHub issue with trigger label (e.g., `automate:devin`)
2. Devin session automatically starts
3. Track progress in dashboard
4. PRs are automatically created

### Automation Types
- **General**: Default automation
- **Dependency Upgrade**: Label with `dependencies`
- **Vulnerability Fix**: Label with `vulnerability` or `security`
- **Bug Fix**: Label with `bug`

## Features

- **Event-Driven**: Webhook triggers on issue creation
- **Real-Time Dashboard**: Kanban board with live status updates
- **Observability**: Session metrics, success rates, ACU tracking
- **GitHub Integration**: PR creation, issue comments, label management
- **Multi-Repository**: Manage multiple repositories with different automation settings

## Architecture

- **Frontend**: React + Vite + shadcn/ui
- **Backend**: FastAPI + GitHub App (PyGithub)
- **Database**: PostgreSQL
- **AI**: Devin API
- **Webhooks**: Smee for local development

## Project Structure

```
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── main.py              # FastAPI app
│   ├── database.py          # SQLAlchemy models
│   ├── github_client.py     # GitHub API
│   └── devin_client.py      # Devin API
├── frontend/
│   └── src/
│       ├── App.jsx          # Main app
│       ├── pages/Settings.jsx
│       └── components/
│           ├── KanbanBoard.jsx
│           └── IssueStats.jsx
```

## License

MIT
