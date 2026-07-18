import { useState, useEffect } from 'react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Switch } from '../components/ui/switch'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Badge } from '../components/ui/badge'
import { Github, Settings as SettingsIcon, Database, Webhook, Loader2, CheckCircle, AlertCircle, ArrowLeft } from 'lucide-react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function Settings({ onBack }) {
  const [installations, setInstallations] = useState([])
  const [repositories, setRepositories] = useState([])
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState(null)
  
  // GitHub App URL from backend API
  const [installUrl, setInstallUrl] = useState('')
  
  // Devin settings from env vars (configured on backend)
  const devinConfigured = true // Backend handles this via env vars
  
  // Automation settings
  const [automationEnabled, setAutomationEnabled] = useState({})
  const [triggerLabels, setTriggerLabels] = useState({})
  const [labelDrafts, setLabelDrafts] = useState({})

  useEffect(() => {
    fetchInstallUrl()
    fetchInstallations()
    fetchRepositories()
    loadSavedSettings()
  }, [])

  const fetchInstallUrl = async () => {
    try {
      const response = await axios.get(`${API_URL}/install`)
      setInstallUrl(response.data.install_url)
    } catch (err) {
      console.error('Failed to fetch install URL:', err)
      // Fallback to default
      setInstallUrl('https://github.com/apps/devin-issue-resolver/installations/new')
    }
  }

  const loadSavedSettings = () => {
    // Settings now come from env vars, no local storage needed
  }

  const fetchInstallations = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_URL}/api/installations`)
      setInstallations(response.data.installations || [])
    } catch (err) {
      console.error('Failed to fetch installations:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchRepositories = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_URL}/api/repositories`)
      setRepositories(response.data.repositories || [])
      
      // Initialize automation settings
      const automationSettings = {}
      const labelSettings = {}
      response.data.repositories.forEach(repo => {
        automationSettings[repo.id] = repo.automation_enabled || false
        labelSettings[repo.id] = repo.trigger_labels || ['automate:devin']
      })
      setAutomationEnabled(automationSettings)
      setTriggerLabels(labelSettings)
      setLabelDrafts(prev => ({
        ...prev,
        ...Object.fromEntries(
          Object.entries(labelSettings).map(([repoId, labels]) => [repoId, labels.join(', ')])
        )
      }))
    } catch (err) {
      console.error('Failed to fetch repositories:', err)
    } finally {
      setLoading(false)
    }
  }

  const syncRepositories = async (installationId) => {
    try {
      setSyncing(true)
      await axios.post(`${API_URL}/api/repositories/sync`, null, {
        params: { installation_id: installationId }
      })
      await fetchRepositories()
    } catch (err) {
      setError('Failed to sync repositories')
      console.error(err)
    } finally {
      setSyncing(false)
    }
  }

  const installGitHubApp = () => {
    if (installUrl) {
      window.location.href = installUrl
    }
  }

  const saveAutomationSettings = async (repoId, enabledOverride = null) => {
    const repo = repositories.find(r => r.id === repoId)
    if (!repo) return

    const enabled = enabledOverride !== null ? enabledOverride : (automationEnabled[repoId] || false)
    const labelsText = labelDrafts[repoId] ?? (triggerLabels[repoId] || ['automate:devin']).join(', ')
    const labels = labelsText
      .split(',')
      .map(label => label.trim())
      .filter(Boolean)

    try {
      await axios.put(`${API_URL}/api/repositories/${repoId}/config`, {
        repository_id: repoId,
        repository_full_name: repo.repository_full_name,
        owner_login: repo.owner_login,
        automation_enabled: enabled,
        automation_config: {
          trigger_labels: labels.length > 0 ? labels : ['automate:devin']
        }
      })

      setAutomationEnabled(prev => ({ ...prev, [repoId]: enabled }))
      setTriggerLabels(prev => ({ ...prev, [repoId]: labels.length > 0 ? labels : ['automate:devin'] }))
      setError(null)
    } catch (err) {
      console.error('Failed to update automation:', err)
      setError('Failed to update automation settings')
    }
  }

  const toggleAutomation = async (repoId) => {
    const newEnabled = !automationEnabled[repoId]
    setAutomationEnabled(prev => ({ ...prev, [repoId]: newEnabled }))
    await saveAutomationSettings(repoId, newEnabled)
  }

  const parseLabels = (value) => {
    return value
      .split(',')
      .map(label => label.trim())
      .filter(Boolean)
  }

  const togglePresetLabel = (repoId, label) => {
    const currentValue = labelDrafts[repoId] ?? (triggerLabels[repoId] || ['automate:devin']).join(', ')
    const labels = parseLabels(currentValue)
    const index = labels.indexOf(label)

    if (index >= 0) {
      labels.splice(index, 1)
    } else {
      labels.push(label)
    }

    setLabelDrafts(prev => ({ ...prev, [repoId]: labels.join(', ') }))
  }

  const presetLabels = ['automate:devin', 'bug', 'dependency', 'security', 'help wanted', 'enhancement']

  return (
    <div className="min-h-screen bg-gradient-to-br from-zinc-900 via-zinc-800 to-zinc-900 p-8">
      <div className="max-w-6xl mx-auto">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold text-white mb-2">Settings</h1>
            <p className="text-zinc-400">Configure your GitHub App and Devin automation settings</p>
          </div>
          <Button
            onClick={onBack}
            variant="outline"
            className="bg-zinc-800 border-zinc-700 text-white hover:bg-zinc-700"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
        </div>

        <Tabs defaultValue="github" className="space-y-6">
          <TabsList className="bg-zinc-800 border-zinc-700">
            <TabsTrigger value="github" className="data-[state=active]:bg-zinc-700">
              <Github className="w-4 h-4 mr-2" />
              GitHub App
            </TabsTrigger>
            <TabsTrigger value="devin" className="data-[state=active]:bg-zinc-700">
              <Database className="w-4 h-4 mr-2" />
              Devin Configuration
            </TabsTrigger>
            <TabsTrigger value="automation" className="data-[state=active]:bg-zinc-700">
              <Webhook className="w-4 h-4 mr-2" />
              Automation Settings
            </TabsTrigger>
          </TabsList>

          {/* GitHub App Tab */}
          <TabsContent value="github" className="space-y-6">
            <Card className="bg-zinc-800/50 border-zinc-700">
              <CardHeader>
                <CardTitle className="text-white">GitHub App Installation</CardTitle>
                <CardDescription className="text-zinc-400">
                  Install the GitHub App to enable automation on your repositories
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {installations.length === 0 ? (
                  <div className="text-center py-8">
                    <AlertCircle className="w-12 h-12 text-zinc-600 mx-auto mb-4" />
                    <p className="text-zinc-400 mb-4">No GitHub App installations found</p>
                    <Button
                      onClick={installGitHubApp}
                      className="bg-zinc-700 hover:bg-zinc-600 text-white"
                    >
                      <Github className="w-4 h-4 mr-2" />
                      Install GitHub App
                    </Button>
                  </div>
                ) : (

                  <div className="mt-6">
                    <h3 className="text-lg font-semibold text-white mb-4">Installed Accounts</h3>
                    <div className="space-y-3">
                      {installations.map((inst) => (
                        <div key={inst.id} className="flex items-center justify-between p-4 bg-zinc-700/50 rounded-lg">
                          <div className="flex items-center gap-3">
                            <CheckCircle className="w-5 h-5 text-green-400" />
                            <div>
                              <p className="text-white font-medium">{inst.github_account_login}</p>
                              <p className="text-sm text-zinc-400">{inst.account_type}</p>
                            </div>
                          </div>
                          <Button
                            onClick={() => syncRepositories(inst.id)}
                            disabled={syncing}
                            variant="outline"
                            size="sm"
                            className="bg-zinc-700 hover:bg-zinc-600 text-white border-zinc-600"
                          >
                            {syncing ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Sync Repos'}
                          </Button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Devin Configuration Tab */}
          <TabsContent value="devin" className="space-y-6">
            <Card className="bg-zinc-800/50 border-zinc-700">
              <CardHeader>
                <CardTitle className="text-white">Devin API Configuration</CardTitle>
                <CardDescription className="text-zinc-400">
                  Devin API credentials are configured via environment variables on the backend
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {devinConfigured ? (
                  <div className="p-4 bg-green-500/20 border border-green-500 rounded-lg">
                    <div className="flex items-center gap-2">
                      <CheckCircle className="w-5 h-5 text-green-400" />
                      <p className="text-green-200">Devin is configured and ready</p>
                    </div>
                  </div>
                ) : (
                  <div className="p-4 bg-yellow-500/20 border border-yellow-500 rounded-lg">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="w-5 h-5 text-yellow-400" />
                      <p className="text-yellow-200">Devin API credentials not configured in environment</p>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Automation Settings Tab */}
          <TabsContent value="automation" className="space-y-6">
            <Card className="bg-zinc-800/50 border-zinc-700">
              <CardHeader>
                <CardTitle className="text-white">Repository Automation</CardTitle>
                <CardDescription className="text-zinc-400">
                  Configure automation settings for each repository
                </CardDescription>
              </CardHeader>
              <CardContent>
                {repositories.length === 0 ? (
                  <div className="text-center py-8">
                    <AlertCircle className="w-12 h-12 text-zinc-600 mx-auto mb-4" />
                    <p className="text-zinc-400">No repositories available</p>
                    <p className="text-sm text-zinc-500 mt-2">Install and sync the GitHub App first</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {repositories.map((repo) => {
                      const repoLabels = parseLabels(labelDrafts[repo.id] ?? (triggerLabels[repo.id] || ['automate:devin']).join(', '))
                      const isEnabled = automationEnabled[repo.id] || false

                      return (
                        <div key={repo.id} className="p-4 bg-zinc-700/50 rounded-lg space-y-4">
                          <div className="flex items-start justify-between gap-4">
                            <div>
                              <p className="text-white font-medium">{repo.repository_full_name}</p>
                              <p className="text-sm text-zinc-400">{repo.owner_login}</p>
                              <p className={`mt-2 text-xs font-medium ${isEnabled ? 'text-emerald-300' : 'text-zinc-400'}`}>
                                {isEnabled ? 'Automatic launching enabled' : 'Automatic launching disabled'}
                              </p>
                            </div>
                            <div className="flex items-center gap-3">
                              <span className="text-sm text-zinc-300">Auto-launch</span>
                              <Switch
                                checked={isEnabled}
                                onCheckedChange={() => toggleAutomation(repo.id)}
                                aria-label={`Toggle auto-launch for ${repo.repository_full_name}`}
                                className="border-zinc-400 bg-zinc-700 data-[state=checked]:bg-emerald-500 data-[state=unchecked]:bg-zinc-600"
                              />
                            </div>
                          </div>

                          <div className={`rounded-lg border p-4 space-y-3 ${isEnabled ? 'border-zinc-600 bg-zinc-800/60' : 'border-zinc-700 bg-zinc-800/30'}`}>
                            <div>
                              <label className="block text-sm font-medium text-zinc-200">
                                Launch when issues have these labels
                              </label>
                              <p className="mt-1 text-xs text-zinc-400">
                                Pick presets or enter your own labels. Issues matching any label will trigger Devin automatically.
                              </p>
                            </div>

                            <div className="flex flex-wrap gap-2">
                              {presetLabels.map((label) => {
                                const isActive = repoLabels.includes(label)
                                return (
                                  <button
                                    key={label}
                                    type="button"
                                    onClick={() => togglePresetLabel(repo.id, label)}
                                    className={`rounded-full border px-3 py-1 text-sm transition ${
                                      isActive
                                        ? 'border-emerald-400 bg-emerald-500/20 text-emerald-200'
                                        : 'border-zinc-600 bg-zinc-700 text-zinc-200 hover:bg-zinc-600'
                                    }`}
                                  >
                                    {label}
                                  </button>
                                )
                              })}
                            </div>

                            <input
                              value={labelDrafts[repo.id] ?? (triggerLabels[repo.id] || ['automate:devin']).join(', ')}
                              onChange={(event) => setLabelDrafts(prev => ({ ...prev, [repo.id]: event.target.value }))}
                              className="w-full rounded-md border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-white outline-none focus:border-zinc-400"
                              placeholder="automate:devin, bug"
                            />

                            <div className="flex flex-wrap gap-2">
                              {repoLabels.map((label) => (
                                <Badge key={label} variant="secondary" className="bg-zinc-600 text-white">{label}</Badge>
                              ))}
                            </div>

                            <div className="flex items-center justify-between">
                              <p className="text-xs text-zinc-500">
                                {isEnabled ? 'These labels will auto-start Devin sessions.' : 'Enable auto-launch first, then save your label preferences.'}
                              </p>
                              <Button
                                size="sm"
                                variant="outline"
                                className="bg-zinc-700 hover:bg-zinc-600 text-white border-zinc-600"
                                onClick={() => saveAutomationSettings(repo.id)}
                              >
                                Save
                              </Button>
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {error && (
          <div className="mt-6 p-4 bg-red-500/20 border border-red-500 rounded-lg text-red-200">
            {error}
          </div>
        )}
      </div>
    </div>
  )
}

export default Settings
