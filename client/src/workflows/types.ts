export type WorkflowSummary = { workflow_id: string; name: string; version: number; description: string; entry_rule_id: string }
export type Condition = { action: string; field: string; equals: string | boolean | number }
export type Branch = { all: Condition[]; next_rule: string | null; outcome: string | null }
export type WorkflowAction = { action_id: string; code: string; name: string; instructions: string; actor: string; timing: string; expected_result: Record<string, { type: string; required: boolean; enum?: string[] }> }
export type WorkflowRule = { rule_id: string; name: string; description: string; actions: WorkflowAction[]; branches: Branch[] }
export type WorkflowDefinition = WorkflowSummary & { rules: WorkflowRule[] }
export function branchLabel(branch: Branch) {
  return branch.all.length ? branch.all.map(condition => `${condition.action}.${condition.field} = ${JSON.stringify(condition.equals)}`).join(' AND ') : 'All checklist items complete'
}
