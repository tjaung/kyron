import { Card, Table } from '../../components'
import type { OverlayLayoutProps } from '../overlayRegistry'
import { branchLabel } from '../../workflows/types'
import type { WorkflowRule } from '../../workflows/types'
export type RuleDetailsData = { rule: WorkflowRule; workflowName: string; ruleNames: Record<string, string> }
export function RuleDetails({ data: { rule, workflowName, ruleNames } }: OverlayLayoutProps<RuleDetailsData>) {
  return <div className="ui-stack rule-details">
    <p className="eyebrow">{workflowName}</p><h3>{rule.name}</h3><p>{rule.description}</p>
    <p className="simulation-note">Every action below is required. They may be completed in any order; missing or invalid results block advancement.</p>
    {rule.actions.map(action => <Card key={action.action_id} variant="muted">
      <h4>{action.name}</h4><p className="rule-action-meta">{action.actor.replaceAll('_', ' ')} · {action.timing.replaceAll('_', ' ')}</p>
      <p>{action.instructions}</p>
      <Table data={Object.entries(action.expected_result).map(([name, spec]) => ({ name, ...spec }))} rowKey={field => field.name}
        columns={[{ id: 'name', name: 'Return field', data: 'name' }, { id: 'type', name: 'Type', data: 'type' }, { id: 'required', name: 'Required', data: field => field.required ? 'Yes' : 'No' }, { id: 'values', name: 'Allowed values', data: field => field.enum?.join(', ') ?? 'Recorded evidence' }]}
        caption={`Expected return values for ${action.name}`} variant="compact" />
    </Card>)}
    <h4>Next steps</h4>
    {rule.branches.map((branch, index) => <Card key={index}>
      <p className="rule-condition">{branchLabel(branch)}</p>
      <strong>→ {branch.next_rule ? ruleNames[branch.next_rule] ?? branch.next_rule : branch.outcome?.replaceAll('_', ' ')}</strong>
    </Card>)}
  </div>
}
