import { useEffect, useState } from 'react'
import type { WorkflowDefinition } from '../workflows/types'
export type Observation = { rule_id: string; action_id: string; status: string; result: Record<string, unknown>; evidence: string; missing_fields: string[]; invalid_fields: string[] }
export type WorkflowProgress = { workflow_id: string; status: string; current_rule_id: string; completed_rules: string[]; observations: Observation[] }
export type ActionTask = { task_id: string; kind: string; target: string; description: string; workflow_code: string | null; status: string; result: Record<string, unknown> }
export type ActionSnapshot = { tasks: ActionTask[]; status: string; definition: WorkflowDefinition | null; run: WorkflowProgress | null; parent_conversation_id: string | null; next_conversation_id: string | null; analysis: {
  summary: string | null; overall_sentiment: string | null; actions_needed: string[] | null; metrics: Record<string, unknown> | null;
  next_action: { target: string; objective: string } | null; decision: string | null; model: string | null
} | null }
export function useConversationActions(practice: string, id: string) {
  const [data, setData] = useState<ActionSnapshot | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const response = await fetch(`/api/practices/${encodeURIComponent(practice)}/conversations/${id}/actions`, { credentials: 'include', signal: controller.signal })
        if (!response.ok) throw new Error('Could not load workflow progress. Retrying…')
        const snapshot = await response.json() as ActionSnapshot
        if (controller.signal.aborted) return
        setData(snapshot); setError('')
      } catch (cause) { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Could not load actions.') }
      finally { if (!controller.signal.aborted) timer = setTimeout(poll, 2000) }
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [practice, id, revision])
  return { data, error, refresh: () => setRevision(value => value + 1) }
}
