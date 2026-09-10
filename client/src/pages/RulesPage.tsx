import { useEffect, useState } from 'react'
import { useAuth } from '../auth/useAuth'
import { Button, Tabs } from '../components'
import { useDataRevision } from '../hooks/useDataRevision'
import { useDrawer } from '../hooks/useDrawer'
import { overlayRegistry } from '../hooks/registry'
import { DecisionTree } from '../workflows/DecisionTree'
import type { WorkflowDefinition, WorkflowSummary } from '../workflows/types'

function WorkflowTree({ practice, workflowId }: { practice: string; workflowId: string }) {
  const [definition, setDefinition] = useState<WorkflowDefinition | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const { openDrawer } = useDrawer()
  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/practices/${encodeURIComponent(practice)}/workflows/${workflowId}`, { credentials: 'include', signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error('Could not load workflow rules.'); return response.json() as Promise<WorkflowDefinition> })
      .then(data => { setDefinition(data); setError('') })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not load rules.') })
    return () => controller.abort()
  }, [practice, workflowId, attempt])
  if (error) return <div className="ui-stack"><p role="alert" className="error">{error}</p><Button variant="outline" onClick={() => setAttempt(value => value + 1)}>Retry</Button></div>
  if (!definition) return <p role="status">Loading decision tree…</p>
  return <DecisionTree definition={definition} onRuleClick={rule => openDrawer(overlayRegistry.ruleDetails, {
    rule, workflowName: `${definition.name} · v${definition.version}`, ruleNames: Object.fromEntries(definition.rules.map(row => [row.rule_id, row.name])),
  })} />
}
export function RulesPage() {
  const { session } = useAuth()
  const practice = session!.practice.slug
  const revision = useDataRevision()
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([])
  const [selected, setSelected] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/practices/${encodeURIComponent(practice)}/workflows`, { credentials: 'include', signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error('Could not load workflows.'); return response.json() as Promise<WorkflowSummary[]> })
      .then(data => { setWorkflows(data); setError(''); setLoading(false) })
      .catch((cause: unknown) => { if (!controller.signal.aborted) { setError(cause instanceof Error ? cause.message : 'Could not load workflows.'); setLoading(false) } })
    return () => controller.abort()
  }, [practice, revision, attempt])
  const value = workflows.some(workflow => workflow.workflow_id === selected) ? selected : workflows[0]?.workflow_id ?? ''
  return <div className="practice-page rules-page">
    <p className="eyebrow">{session!.practice.name}</p><h1>Rules</h1>
    <p className="muted">Explore workflow decisions and the required action checklists behind them.</p>
    {error ? <div className="ui-stack"><p role="alert" className="error">{error}</p><Button variant="outline" onClick={() => setAttempt(value => value + 1)}>Retry</Button></div>
      : loading ? <p role="status">Loading workflows…</p>
      : !workflows.length ? <p>No workflows yet. Use Seed data to populate the workflow catalog.</p>
      : <Tabs label="Workflows" value={value} onValueChange={setSelected} keepMounted={false} items={workflows.map(workflow => ({
        value: workflow.workflow_id, label: `${workflow.name} · v${workflow.version}`, content: <div className="workflow-view">
          <p className="muted">{workflow.description}</p>
          <WorkflowTree key={`${workflow.workflow_id}:${revision}`} practice={practice} workflowId={workflow.workflow_id} />
        </div>,
      }))} />}
  </div>
}
