import { Card, CardHeader, CardTitle, CardContent } from './ui/card'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line } from 'recharts'
import { TrendingUp, AlertCircle, CheckCircle, Clock, Activity, Zap } from 'lucide-react'

const IssueStats = ({ issues, sessions, metrics = [], selectedRepo }) => {
  const openIssues = issues.filter(i => i.state === 'open')
  const closedIssues = issues.filter(i => i.state === 'closed')

  // Filter sessions by selected repository if provided
  const filteredSessions = selectedRepo
    ? sessions.filter(s => s.repository_full_name === selectedRepo)
    : sessions

  // Filter metrics by selected repository if provided
  const filteredMetrics = selectedRepo
    ? metrics.filter(m => m.repository_full_name === selectedRepo)
    : metrics

  // Session-based categorization
  const activeSessions = filteredSessions.filter(s => {
    const hasPR = s.pull_requests && s.pull_requests.length > 0
    return !hasPR && ['new', 'claimed', 'running', 'resuming', 'suspended'].includes(s.status)
  })
  const completedSessions = filteredSessions.filter(s => {
    const hasPR = s.pull_requests && s.pull_requests.length > 0
    return s.status === 'exit' || hasPR
  })
  const failedSessions = filteredSessions.filter(s => s.status === 'error')
  
  const totalACUs = filteredSessions.reduce((acc, s) => acc + (s.acus_consumed || 0), 0)
  const avgACUs = filteredSessions.length > 0 ? totalACUs / filteredSessions.length : 0

  // Average completion time
  const completionTimes = filteredSessions
    .filter(s => s.completed_at && s.created_at)
    .map(s => {
      const created = new Date(s.created_at)
      const completed = new Date(s.completed_at)
      return (completed - created) / 1000 / 60 // in minutes
    })
  const avgCompletionTime = completionTimes.length > 0
    ? Math.round(completionTimes.reduce((a, b) => a + b, 0) / completionTimes.length)
    : 0

  // ACU efficiency (ACU per successful session)
  const successfulSessionsWithACU = completedSessions.filter(s => s.acus_consumed > 0)
  const acuEfficiency = successfulSessionsWithACU.length > 0
    ? Math.round(successfulSessionsWithACU.reduce((acc, s) => acc + s.acus_consumed, 0) / successfulSessionsWithACU.length)
    : 0

  // Error breakdown
  const errorBreakdown = {}
  failedSessions.forEach(session => {
    const error = session.error_message || session.status_detail || 'unknown'
    const key = error.includes('out_of_credits') ? 'out_of_credits'
              : error.includes('timeout') ? 'timeout'
              : error.includes('rate_limit') ? 'rate_limit'
              : error.includes('permission') ? 'permission'
              : 'other'
    errorBreakdown[key] = (errorBreakdown[key] || 0) + 1
  })

  const errorData = Object.entries(errorBreakdown)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
  
  // Daily throughput trend
  const throughputData = filteredMetrics
    .map(m => ({
      date: new Date(m.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      completed: m.successful_sessions || 0,
      failed: m.failed_sessions || 0
    }))
    .slice(-7) // Last 7 days

  const latestMetric = filteredMetrics.length > 0 ? filteredMetrics[filteredMetrics.length - 1] : null
  const aggregatedSuccessRate = latestMetric && latestMetric.total_sessions > 0
    ? Math.round((latestMetric.successful_sessions / latestMetric.total_sessions) * 100)
    : (filteredSessions.length > 0 ? Math.round((completedSessions.length / filteredSessions.length) * 100) : 0)
  const aggregatedACUs = latestMetric ? latestMetric.total_acus_consumed : totalACUs
  const aggregatedCompleted = latestMetric ? latestMetric.successful_sessions : completedSessions.length
  const aggregatedFailed = latestMetric ? latestMetric.failed_sessions : failedSessions.length

  // Prepare data for bar chart - issues by label
  const labelCounts = {}
  issues.forEach(issue => {
    issue.labels?.forEach(label => {
      const labelName = typeof label === 'string' ? label : label.name
      labelCounts[labelName] = (labelCounts[labelName] || 0) + 1
    })
  })

  const barData = Object.entries(labelCounts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 6)

  // Prepare data for pie chart - session status
  const pieData = [
    { name: 'Active', value: activeSessions.length, color: '#3b82f6' },
    { name: 'Completed', value: completedSessions.length, color: '#22c55e' },
    { name: 'Failed', value: failedSessions.length, color: '#ef4444' }
  ]

  return (
    <div className="space-y-6">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <Card className="bg-slate-800/50 border-slate-700 backdrop-blur-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-slate-400">Total Issues</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-purple-400" />
              <span className="text-3xl font-bold text-white">{issues.length}</span>
            </div>
            <p className="text-xs text-slate-500 mt-1">{openIssues.length} open</p>
          </CardContent>
        </Card>

        <Card className="bg-slate-800/50 border-slate-700 backdrop-blur-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-slate-400">Active Sessions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-blue-400" />
              <span className="text-3xl font-bold text-white">{activeSessions.length}</span>
            </div>
            <p className="text-xs text-slate-500 mt-1">{completedSessions.length} completed</p>
          </CardContent>
        </Card>

        <Card className="bg-slate-800/50 border-slate-700 backdrop-blur-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-slate-400">Success Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-green-400" />
              <span className="text-3xl font-bold text-white">
                {aggregatedSuccessRate}%
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">{aggregatedFailed} failed</p>
          </CardContent>
        </Card>

        <Card className="bg-slate-800/50 border-slate-700 backdrop-blur-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-slate-400">Avg Completion Time</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <Clock className="w-5 h-5 text-orange-400" />
              <span className="text-3xl font-bold text-white">
                {avgCompletionTime}m
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">per session</p>
          </CardContent>
        </Card>
      </div>

      {/* Charts - 2 column grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="bg-slate-800/50 border-slate-700 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-white">Issues by Label</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={barData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} />
                <Tooltip
                  contentStyle={{ backgroundColor: 'transparent', border: 'none', borderRadius: '8px' }}
                  itemStyle={{ color: '#fff' }}
                  cursor={{ fill: 'transparent' }}
                />
                <Bar dataKey="count" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card className="bg-slate-800/50 border-slate-700 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-white">Session Status</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={80}
                paddingAngle={5}
                dataKey="value"
              >
                {pieData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
                itemStyle={{ color: '#fff' }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-4 mt-2">
            {pieData.map((entry) => (
              <div key={entry.name} className="flex items-center gap-1">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: entry.color }} />
                <span className="text-xs text-slate-400">{entry.name}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

        {errorData.length > 0 && (
          <Card className="bg-slate-800/50 border-slate-700 backdrop-blur-sm">
            <CardHeader>
              <CardTitle className="text-white">Error Breakdown</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={errorData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="count"
                  >
                    {errorData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={['#ef4444', '#f97316', '#eab308', '#8b5cf6', '#6b7280'][index % 5]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
                    itemStyle={{ color: '#fff' }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex justify-center gap-4 mt-2 flex-wrap">
                {errorData.map((entry) => (
                  <div key={entry.name} className="flex items-center gap-1">
                    <div className="w-3 h-3 rounded-full bg-red-500" />
                    <span className="text-xs text-slate-400">{entry.name}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        <Card className="md:col-span-2 bg-slate-800/50 border-slate-700 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-white">Daily Throughput (7 days)</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={throughputData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="date" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
                  itemStyle={{ color: '#fff' }}
                />
                <Line type="monotone" dataKey="completed" stroke="#22c55e" strokeWidth={2} name="Completed" />
                <Line type="monotone" dataKey="failed" stroke="#ef4444" strokeWidth={2} name="Failed" />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export default IssueStats
