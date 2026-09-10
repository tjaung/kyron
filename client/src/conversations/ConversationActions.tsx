import { useState } from 'react'
import { Table } from '../components'
import { DecisionTree } from '../workflows/DecisionTree'
import type { ActionSnapshot } from '../hooks/useConversationActions'
export function ConversationActions({ data }: { data: ActionSnapshot | null }) {
  const [selected, setSelected] = useState<string | null>(null)
  if (!data) return <p role="status">Loading workflow progress…</p>
  if (!data.run || !data.definition) return <p>This conversation has no recorded workflow run.</p>
  const { run, definition } = data
  const latest = new Map(run.observations.map(row => [`${row.rule_id}:${row.action_id}`, row]))
  const rule = definition.rules.find(row => row.rule_id === (selected ?? run.current_rule_id))
  const rows = (rule ? [rule] : definition.rules).flatMap(rule => rule.actions.map(action => {
    const observation = latest.get(`${rule.rule_id}:${action.action_id}`)
    return { id: `${rule.rule_id}:${action.action_id}`, name: action.name, instructions: action.instructions,
      status: observation ? observation.status === 'completed' && !observation.missing_fields.length && !observation.invalid_fields.length ? 'Completed' : `${observation.status} — incomplete or invalid evidence` : 'Not done',
      evidence: observation?.evidence ?? 'No evidence recorded', result: observation ? JSON.stringify(observation.result) : '—',
      missing: [...observation?.missing_fields ?? [], ...observation?.invalid_fields ?? []].join(', ') || '—' }
  }))
  return <div className="ui-stack conversation-actions">
    <Table data={data.tasks ?? []} rowKey={task => task.task_id} header={{ title: 'Actions chosen by the AI', subtitle: 'Simulated operations and delivery receipts. Calls launch another conversation.' }}
      columns={[{ id: 'kind', name: 'Operation', data: 'kind' }, { id: 'target', name: 'Recipient', data: 'target' },
        { id: 'description', name: 'Action', data: 'description' }, { id: 'workflow', name: 'Workflow', data: 'workflow_code' },
        { id: 'status', name: 'Status', data: 'status' }, { id: 'result', name: 'Result', data: task => JSON.stringify(task.result) }]} />
    <p>Workflow: <strong>{run.status.replaceAll('_', ' ')}</strong>. Green shows completed rules and the path taken; yellow marks the current rule. Other rules have not been taken.</p>
    <DecisionTree definition={definition} progress={run} onRuleClick={rule => setSelected(rule.rule_id)} />
    <Table data={rows} rowKey={row => row.id} header={{ title: rule?.name ?? 'Checklist', subtitle: 'Select a rule above to inspect recorded and missing work.' }}
      columns={[{ id: 'name', name: 'Action', data: 'name' }, { id: 'status', name: 'Status', data: 'status' },
        { id: 'evidence', name: 'Evidence', data: 'evidence' }, { id: 'result', name: 'Return value', data: 'result' }, { id: 'missing', name: 'Missing / invalid', data: 'missing' }]} />
    {data.analysis?.actions_needed?.length ? <div><h4>Outstanding work</h4><ul>{data.analysis.actions_needed.map((action, i) => <li key={i}>{action}</li>)}</ul></div> : null}
    {data.analysis?.next_action && <p>Next contact: <strong>{data.analysis.next_action.target.replaceAll('_', ' ')}</strong> — {data.analysis.next_action.objective}</p>}
    {data.next_conversation_id && <p>Follow-up conversation: <code>{data.next_conversation_id}</code></p>}
  </div>
}
