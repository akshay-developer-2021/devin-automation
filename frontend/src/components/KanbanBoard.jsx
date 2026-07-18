import { Card, CardHeader, CardTitle, CardContent } from './ui/card'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Clock, User, Play, Activity, CheckCircle, XCircle, ExternalLink, Loader2 } from 'lucide-react'

const KanbanBoard = ({ issues, sessions, onStartDevinSession, loadingSession }) => {
  const getSessionForIssue = (issueNumber) => {
    return sessions.find(s => s.issue_number === issueNumber)
  }

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A'
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  const getSessionStatusBadge = (session) => {
    if (!session) return null

    // Check if session has PRs - consider it completed regardless of status
    const hasPR = session?.pull_requests && session.pull_requests.length > 0
    if (hasPR) {
      return (
        <Badge className="bg-green-500 text-white">
          Completed
        </Badge>
      )
    }

    const statusConfig = {
      'new': { color: 'bg-slate-500', text: 'New' },
      'claimed': { color: 'bg-blue-500', text: 'Claimed' },
      'running': { color: 'bg-yellow-500', text: 'Running' },
      'exit': { color: 'bg-green-500', text: 'Completed' },
      'error': { color: 'bg-red-500', text: 'Error' },
      'suspended': { color: 'bg-orange-500', text: 'Suspended' },
      'resuming': { color: 'bg-purple-500', text: 'Resuming' }
    }

    const config = statusConfig[session.status] || statusConfig['new']
    return (
      <Badge className={`${config.color} text-white`}>
        {config.text}
      </Badge>
    )
  }

  // Categorize issues based on session status and GitHub state
  const todoIssues = issues.filter(issue => {
    if (issue.state === 'closed') return false
    const session = getSessionForIssue(issue.number)
    return !session || session.status === 'error'
  })

  const inProgressIssues = issues.filter(issue => {
    if (issue.state === 'closed') return false
    const session = getSessionForIssue(issue.number)
    // Exclude sessions with PRs (they're considered completed regardless of status)
    const hasPR = session?.pull_requests && session.pull_requests.length > 0
    if (hasPR) return false
    return session && ['new', 'claimed', 'running', 'resuming', 'suspended'].includes(session.status)
  })

  const completedIssues = issues.filter(issue => {
    if (issue.state === 'closed') return true
    const session = getSessionForIssue(issue.number)
    // Consider session completed if it's exit, or has a PR (any status)
    const hasPR = session?.pull_requests && session.pull_requests.length > 0
    return session && (session.status === 'exit' || hasPR)
  })

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* To Do Column */}
      <div className="bg-zinc-800/50 rounded-xl p-4 backdrop-blur-sm border border-zinc-700">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-zinc-500" />
          To Do
          <span className="text-sm text-zinc-400">({todoIssues.length})</span>
        </h3>
        <div className="space-y-3">
          {todoIssues.map(issue => (
            <Card key={issue.id} className="bg-zinc-700/50 border-zinc-600 hover:border-zinc-500 transition-colors">
              <CardHeader className="pb-3">
                <CardTitle className="text-white text-base font-medium line-clamp-2">
                  {issue.title}
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="flex flex-wrap gap-1 mb-3">
                  {issue.labels?.slice(0, 3).map(label => (
                    <Badge key={label.name} variant="secondary" className="text-xs bg-zinc-600 text-white">
                      {label.name}
                    </Badge>
                  ))}
                </div>
                <div className="flex items-center justify-between text-xs text-zinc-400 mb-3">
                  <div className="flex items-center gap-1">
                    <User className="w-3 h-3" />
                    {issue.user?.login}
                  </div>
                  <div className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {formatDate(issue.created_at)}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    onClick={() => onStartDevinSession(issue.number)}
                    disabled={loadingSession === issue.number}
                    className="flex-1 bg-zinc-700 hover:bg-zinc-600 text-white text-xs"
                    size="sm"
                  >
                    {loadingSession === issue.number ? (
                      <>
                        <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                        Starting...
                      </>
                    ) : (
                      <>
                        <Play className="w-3 h-3 mr-1" />
                        Start Devin
                      </>
                    )}
                  </Button>
                  <Button
                    onClick={() => window.open(issue.html_url, '_blank')}
                    className="flex-1 bg-zinc-700 hover:bg-zinc-600 text-white text-xs"
                    size="sm"
                  >
                    <ExternalLink className="w-3 h-3 mr-1" />
                    View Issue
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* In Progress Column */}
      <div className="bg-zinc-800/50 rounded-xl p-4 backdrop-blur-sm border border-zinc-700">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-blue-500" />
          In Progress
          <span className="text-sm text-zinc-400">({inProgressIssues.length})</span>
        </h3>
        <div className="space-y-3">
          {inProgressIssues.map(issue => {
            const session = getSessionForIssue(issue.number)
            return (
              <Card key={issue.id} className="bg-zinc-700/50 border-zinc-600 hover:border-zinc-500 transition-colors">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <CardTitle className="text-white text-base font-medium line-clamp-2">
                      {issue.title}
                    </CardTitle>
                    {getSessionStatusBadge(session)}
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="flex flex-wrap gap-1 mb-3">
                    {issue.labels?.slice(0, 3).map(label => (
                      <Badge key={label.name} variant="secondary" className="text-xs bg-zinc-600 text-white">
                        {label.name}
                      </Badge>
                    ))}
                  </div>
                  <div className="flex items-center justify-between text-xs text-zinc-400 mb-3">
                    <div className="flex items-center gap-1">
                      <User className="w-3 h-3" />
                      {issue.user?.login}
                    </div>
                    <div className="flex items-center gap-1">
                      <Activity className="w-3 h-3" />
                      {session?.acus_consumed?.toFixed(1) || 0} ACUs
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      onClick={() => window.open(issue.html_url, '_blank')}
                      className="flex-1 bg-zinc-600 hover:bg-zinc-700 text-white text-xs"
                      size="sm"
                    >
                      <ExternalLink className="w-3 h-3 mr-1" />
                      View Issue
                    </Button>
                    {session?.session_url && (
                      <Button
                        onClick={() => window.open(session.session_url, '_blank')}
                        className="flex-1 bg-zinc-600 hover:bg-zinc-700 text-white text-xs"
                        size="sm"
                      >
                        <ExternalLink className="w-3 h-3 mr-1" />
                        View Session
                      </Button>
                    )}
                  </div>
                  <div className="space-y-2">
                    {session?.status && (
                      <div className="rounded-md border border-zinc-600 bg-zinc-800/70 px-2 py-2 text-xs text-zinc-300">
                        <div className="font-medium text-white">Session status</div>
                        <div className="mt-1">{session.status}</div>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </div>

      {/* Completed Column */}
      <div className="bg-zinc-800/50 rounded-xl p-4 backdrop-blur-sm border border-zinc-700">
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-green-500" />
          Completed
          <span className="text-sm text-zinc-400">({completedIssues.length})</span>
        </h3>
        <div className="space-y-3">
          {completedIssues.map(issue => {
            const session = getSessionForIssue(issue.number)
            return (
              <Card key={issue.id} className="bg-zinc-700/50 border-zinc-600 opacity-75">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <CardTitle className="text-zinc-300 text-base font-medium line-clamp-2">
                      {issue.title}
                    </CardTitle>
                    <CheckCircle className="w-4 h-4 text-green-400" />
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="flex flex-wrap gap-1 mb-3">
                    {issue.labels?.slice(0, 3).map(label => (
                      <Badge key={label.name} variant="secondary" className="text-xs bg-zinc-600 text-white">
                        {label.name}
                      </Badge>
                    ))}
                  </div>
                  <div className="flex items-center justify-between text-xs text-zinc-400 mb-3">
                    <div className="flex items-center gap-1">
                      <User className="w-3 h-3" />
                      {issue.user?.login}
                    </div>
                    <div className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {formatDate(session?.completed_at)}
                    </div>
                  </div>
                  <div className="flex gap-2 mb-2">
                    <Button
                      onClick={() => window.open(issue.html_url, '_blank')}
                      className="flex-1 bg-zinc-600 hover:bg-zinc-700 text-white text-xs"
                      size="sm"
                    >
                      <ExternalLink className="w-3 h-3 mr-1" />
                      View Issue
                    </Button>
                    {session?.session_url && (
                      <Button
                        onClick={() => window.open(session.session_url, '_blank')}
                        className="flex-1 bg-zinc-600 hover:bg-zinc-700 text-white text-xs"
                        size="sm"
                      >
                        <ExternalLink className="w-3 h-3 mr-1" />
                        View Session
                      </Button>
                    )}
                  </div>
                  <div className="space-y-2">
                    {session?.status && (
                      <div className="rounded-md border border-zinc-600 bg-zinc-800/70 px-2 py-2 text-xs text-zinc-300">
                        <div className="font-medium text-white">Session status</div>
                        <div className="mt-1">{session.status}</div>
                      </div>
                    )}
                    {session?.pull_requests && session.pull_requests.length > 0 && (
                      <div className="space-y-2">
                        {session.pull_requests.map(pr => (
                          <Button
                            key={pr.pr_url}
                            onClick={() => window.open(pr.pr_url, '_blank')}
                            className="w-full bg-green-600 hover:bg-green-700 text-white text-xs"
                            size="sm"
                          >
                            <ExternalLink className="w-3 h-3 mr-1" />
                            View PR #{pr.pr_url?.split('/').pop()}
                          </Button>
                        ))}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default KanbanBoard
