import { useState, useEffect } from 'react'
import { Kanban, Github, Settings as SettingsIcon, Loader2 } from 'lucide-react'
import axios from 'axios'
import KanbanBoard from './components/KanbanBoard'
import IssueStats from './components/IssueStats'
import Settings from './pages/Settings'
import { Button } from './components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './components/ui/select'
import { useToast, Toast } from './components/ui/toast'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function App() {
  const [currentPage, setCurrentPage] = useState('dashboard')
  const [repositories, setRepositories] = useState([])
  const [selectedRepo, setSelectedRepo] = useState('')
  const [issues, setIssues] = useState([])
  const [sessions, setSessions] = useState([])
  const [metrics, setMetrics] = useState([])
  const [installations, setInstallations] = useState([])
  const [syncingRepos, setSyncingRepos] = useState(false)
  const [error, setError] = useState(null)
  const [loadingSession, setLoadingSession] = useState(null)
  const { toast, showToast, hideToast } = useToast()

  // Load selected repo from query params on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const repoParam = params.get('repo')
    if (repoParam) {
      setSelectedRepo(repoParam)
    }
  }, [])

  // Update query params when selected repo changes
  useEffect(() => {
    if (selectedRepo) {
      const url = new URL(window.location)
      url.searchParams.set('repo', selectedRepo)
      window.history.replaceState({}, '', url)
    }
  }, [selectedRepo])

  useEffect(() => {
    if (currentPage === 'dashboard') {
      fetchInstallations()
      fetchRepositories()
      fetchSessions()
      fetchMetrics()
    }
  }, [currentPage])

  useEffect(() => {
    if (currentPage !== 'dashboard') return

    // Check if installation_id is in query params (post-installation flow)
    const params = new URLSearchParams(window.location.search)
    const installationId = params.get('installation_id')
    
    // Set syncing state based on installation_id
    if (installationId && repositories.length === 0) {
      setSyncingRepos(true)
    } else {
      setSyncingRepos(false)
    }

    // Normal polling for issues, metrics, sessions (10 seconds)
    const normalInterval = setInterval(async () => {
      if (selectedRepo) {
        fetchIssues(selectedRepo)
      }
      fetchMetrics()
      fetchSessions()
    }, 10000)

    // Faster polling for repos when installation_id present (2 seconds)
    let repoInterval = null
    if (installationId && repositories.length === 0) {
      repoInterval = setInterval(async () => {
        await fetchRepositories()
        if (repositories.length > 0) {
          setSyncingRepos(false)
          // Remove all query params after repos are loaded
          const url = new URL(window.location)
          url.search = ''
          window.history.replaceState({}, '', url)
          if (repoInterval) clearInterval(repoInterval)
        }
      }, 2000)
    }
    
    // Only poll installations if we don't have any yet (10 seconds)
    const installInterval = setInterval(async () => {
      if (installations.length === 0) {
        const newInstallations = await fetchInstallations()
        setInstallations(newInstallations)
      }
    }, 10000)

    return () => {
      clearInterval(normalInterval)
      if (repoInterval) clearInterval(repoInterval)
      clearInterval(installInterval)
    }
  }, [currentPage, selectedRepo, repositories.length])

  const fetchRepositories = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/repositories`)
      setRepositories(response.data.repositories || [])
    } catch (err) {
      // If 404 or no repositories, that's expected before installation
      if (err.response?.status !== 404) {
        setError('Failed to fetch repositories')
        console.error(err)
      }
    }
  }

  const fetchInstallations = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/installations`)
      return response.data.installations || []
    } catch (err) {
      console.error('Failed to fetch installations:', err)
      return []
    }
  }


  const fetchSessions = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/sessions`)
      setSessions(response.data.sessions || [])
    } catch (err) {
      console.error('Failed to fetch sessions:', err)
    }
  }

  const fetchMetrics = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/metrics`)
      setMetrics(response.data.metrics || [])
    } catch (err) {
      console.error('Failed to fetch metrics:', err)
    }
  }

  const fetchIssues = async (repo) => {
    if (!repo) return
    
    try {
      setError(null)
      const response = await axios.get(`${API_URL}/api/repositories/${repo}/issues`)
      setIssues(response.data.issues || [])
    } catch (err) {
      setError('Failed to fetch issues')
      console.error(err)
    }
  }

  useEffect(() => {
    if (selectedRepo && currentPage === 'dashboard') {
      fetchIssues(selectedRepo)
    }
  }, [selectedRepo, currentPage])

  const startDevinSession = async (issueNumber, automationType = 'general') => {
    setLoadingSession(issueNumber)
    try {
      await axios.post(`${API_URL}/api/devin/session`, {
        repository_full_name: selectedRepo,
        issue_number: issueNumber,
        automation_type: automationType
      })
      await fetchSessions()
      showToast('Devin session started successfully!', 'success')
    } catch (err) {
      showToast('Failed to start Devin session', 'error')
      console.error(err)
    } finally {
      setLoadingSession(null)
    }
  }

  if (currentPage === 'settings') {
    return <Settings onBack={() => setCurrentPage('dashboard')} />
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-900 via-zinc-800 to-zinc-900">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <header className="mb-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Github className="w-10 h-10 text-zinc-400" />
            <div>
              <h1 className="text-4xl font-bold text-white">Devin Automation</h1>
              <p className="text-zinc-400">AI-powered GitHub issue resolution</p>
            </div>
          </div>
          <Button
            onClick={() => setCurrentPage('settings')}
            variant="outline"
            className="bg-zinc-800 border-zinc-700 text-white hover:bg-zinc-700"
          >
            <SettingsIcon className="w-4 h-4 mr-2" />
            Settings
          </Button>
        </header>

        {/* Repository Selector - only show if repos exist */}
        {repositories.length > 0 && (
          <div className="mb-8">
            <label className="block text-sm font-medium text-zinc-300 mb-2">
              Select Repository
            </label>
            <Select value={selectedRepo} onValueChange={setSelectedRepo}>
              <SelectTrigger className="w-full max-w-md bg-zinc-800 border-zinc-700 text-white focus:ring-2 focus:ring-zinc-500">
                <SelectValue placeholder="Select a repository..." />
              </SelectTrigger>
              <SelectContent className="bg-zinc-800 border-zinc-700">
                {repositories.map((repo) => (
                  <SelectItem key={repo.id} value={repo.repository_full_name} className="text-white focus:bg-zinc-700">
                    {repo.repository_full_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {/* Error Message */}
        {error && (
          <div className="mb-6 p-4 bg-red-500/20 border border-red-500 rounded-lg text-red-200 flex items-center justify-between">
            <span>{error}</span>
            <Button
              onClick={() => setError(null)}
              variant="ghost"
              className="text-red-200 hover:text-red-100"
            >
              Dismiss
            </Button>
          </div>
        )}

        {/* Main Content */}
        {issues.length > 0 && (
          <>
            {/* Stats Section */}
            <div className="mb-8">
              <IssueStats issues={issues} sessions={sessions} metrics={metrics} selectedRepo={selectedRepo} />
            </div>

            {/* Kanban Board */}
            <KanbanBoard
              issues={issues}
              sessions={sessions}
              onStartDevinSession={startDevinSession}
              loadingSession={loadingSession}
            />
          </>
        )}

        {/* Empty States */}
        {issues.length === 0 && (
          <>
            {/* No Repositories State */}
            {repositories.length === 0 && installations.length === 0 && (
              <div className="text-center py-12">
                <Github className="w-16 h-16 text-zinc-600 mx-auto mb-4" />
                <h2 className="text-2xl font-bold text-white mb-2">Welcome to Devin Automation</h2>
                <p className="text-zinc-400 text-lg mb-4">AI-powered GitHub issue resolution</p>
                <p className="text-zinc-500 text-sm mb-6">Install the GitHub App to get started</p>
                <Button
                  onClick={async () => {
                    try {
                      const response = await axios.get(`${API_URL}/install`)
                      window.location.href = response.data.install_url
                    } catch (err) {
                      setError('Failed to get install URL')
                    }
                  }}
                  className="bg-zinc-700 hover:bg-zinc-600"
                >
                  <Github className="w-4 h-4 mr-2" />
                  Install GitHub App
                </Button>
              </div>
            )}

            {/* GitHub Connected but No Repos */}
            {repositories.length === 0 && installations.length > 0 && (
              <div className="text-center py-12">
                <Github className="w-16 h-16 text-zinc-600 mx-auto mb-4" />
                <p className="text-zinc-400 text-lg mb-4">GitHub App Connected</p>
                {syncingRepos ? (
                  <>
                    <p className="text-zinc-500 text-sm mb-6">Syncing your repositories...</p>
                    <Loader2 className="w-6 h-6 text-zinc-400 mx-auto animate-spin" />
                  </>
                ) : (
                  <p className="text-zinc-500 text-sm mb-6">No repositories found</p>
                )}
              </div>
            )}

            {/* No Issues State */}
            {repositories.length > 0 && selectedRepo && (
              <div className="text-center py-12">
                <Kanban className="w-16 h-16 text-zinc-600 mx-auto mb-4" />
                <p className="text-zinc-400 text-lg">No open issues found in this repository</p>
              </div>
            )}
          </>
        )}
      </div>

      {/* Toast */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={hideToast}
        />
      )}
    </div>
  )
}

export default App
