import { useId, useMemo, useState } from 'react'
import type { WorkflowProgress } from '../hooks/useConversationActions'
import { Button } from '../components'
import type { WorkflowDefinition, WorkflowRule, Branch } from './types'
import { branchLabel } from './types'

type Node = { id: string; name: string; rule?: WorkflowRule; level: number; x: number; y: number }
function layout(definition: WorkflowDefinition) {
  const nodes = new Map<string, Node>(definition.rules.map(rule => [rule.rule_id, { id: rule.rule_id, name: rule.name, rule, level: 0, x: 0, y: 0 }]))
  const edges: { from: string; to: string; branch: Branch }[] = []
  for (const rule of definition.rules) for (const branch of rule.branches) {
    const to = branch.next_rule ?? `outcome:${branch.outcome}`
    if (!branch.next_rule) nodes.set(to, { id: to, name: branch.outcome?.replaceAll('_', ' ') ?? 'Outcome', level: 0, x: 0, y: 0 })
    edges.push({ from: rule.rule_id, to, branch })
  }
  const degrees = new Map([...nodes.keys()].map(id => [id, edges.filter(edge => edge.to === id).length]))
  const queue = [...nodes.values()].filter(node => degrees.get(node.id) === 0)
  let visited = 0
  while (queue.length) {
    const node = queue.shift()!
    visited++
    for (const edge of edges.filter(edge => edge.from === node.id)) {
      const next = nodes.get(edge.to)
      if (!next) throw new Error('A workflow branch points to a missing rule.')
      next.level = Math.max(next.level, node.level + 1)
      degrees.set(next.id, degrees.get(next.id)! - 1)
      if (degrees.get(next.id) === 0) queue.push(next)
    }
  }
  if (visited !== nodes.size) throw new Error('This workflow contains a cycle and cannot be displayed as a decision tree.')
  const groups = new Map<number, Node[]>()
  for (const node of nodes.values()) groups.set(node.level, [...groups.get(node.level) ?? [], node])
  const height = Math.max(360, ...[...groups.values()].map(group => group.length * 154 + 60))
  for (const [level, group] of groups) group.sort((a, b) => a.name.localeCompare(b.name)).forEach((node, index) => {
    node.x = 30 + level * 360; node.y = (height - group.length * 154) / 2 + index * 154
  })
  return { nodes, edges, width: groups.size * 360, height }
}
export function DecisionTree({ definition, onRuleClick, progress }: { definition: WorkflowDefinition; progress?: WorkflowProgress; onRuleClick: (rule: WorkflowRule) => void }) {
  const marker = useId()
  const [zoom, setZoom] = useState(0.8)
  const result = useMemo(() => { try { return { graph: layout(definition), error: '' } } catch (error) { return { graph: null, error: error instanceof Error ? error.message : 'Cannot display this workflow.' } } }, [definition])
  if (!result.graph) return <p role="alert" className="error">{result.error}</p>
  const { nodes, edges, width, height } = result.graph
  const path = progress ? [...progress.completed_rules, ...(progress.status === 'active' ? [progress.current_rule_id] : [`outcome:${progress.status}`])] : []
  return <div className="decision-tree">
    <div className="tree-toolbar"><p>Follow the arrows from Start. Select a rule to inspect its checklist.</p><div>
      <Button size="sm" variant="outline" aria-label="Zoom out" disabled={zoom <= .3} onClick={() => setZoom(value => Math.max(.3, value - .1))}>−</Button>
      <span>{Math.round(zoom * 100)}%</span>
      <Button size="sm" variant="outline" aria-label="Zoom in" disabled={zoom >= 1.3} onClick={() => setZoom(value => Math.min(1.3, value + .1))}>+</Button>
      <Button size="sm" variant="ghost" onClick={() => setZoom(.8)}>Reset zoom</Button>
    </div></div>
    <div className="tree-viewport" role="region" aria-label={`${definition.name} decision tree`} tabIndex={0}>
      <div style={{ width: width * zoom, height: height * zoom }}>
        <div className="tree-canvas" style={{ width, height, transform: `scale(${zoom})` }}>
          <svg width={width} height={height} className="tree-edges" aria-hidden="true">
            <defs><marker id={marker} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="currentColor" /></marker></defs>
            {edges.map((edge, index) => {
              const from = nodes.get(edge.from)!, to = nodes.get(edge.to)!
              const x1 = from.x + 220, y1 = from.y + 50, x2 = to.x, y2 = to.y + 50
              const label = edge.branch.all.map(c => `${c.field}: ${String(c.equals)}`).join(' + ') || 'Checklist complete'
              return <g key={index} className={path.some((id, i) => id === edge.from && path[i + 1] === edge.to) && edge.branch.all.every(condition => { const action = nodes.get(edge.from)?.rule?.actions.find(action => action.code === condition.action); return progress?.observations.filter(row => row.rule_id === edge.from && row.action_id === action?.action_id).at(-1)?.result[condition.field] === condition.equals }) ? 'tree-edge--taken' : ''}><title>{branchLabel(edge.branch)}</title>
                <path d={`M${x1},${y1} C${x1 + 70},${y1} ${x2 - 70},${y2} ${x2},${y2}`} markerEnd={`url(#${marker})`} />
                <text x={x1 + 8} y={y1 - 12 + index % 3 * 14}>{label.length > 38 ? label.slice(0, 35) + '…' : label}</text>
              </g>
            })}
          </svg>
          {[...nodes.values()].map(node => node.rule ? <button key={node.id} type="button" className={`tree-node ${progress?.completed_rules.includes(node.id) ? 'tree-node--completed' : progress?.current_rule_id === node.id && progress.status === 'active' ? 'tree-node--current' : ''}`} style={{ left: node.x, top: node.y }} onClick={() => onRuleClick(node.rule!)}>
            <span className="eyebrow">{node.id === definition.entry_rule_id ? 'Start · Rule' : 'Rule'}</span><strong>{node.name}</strong><span>{node.rule.actions.length} required action{node.rule.actions.length === 1 ? '' : 's'}</span>
          </button> : <div key={node.id} className={`tree-node tree-outcome ${node.id === `outcome:${progress?.status}` ? 'tree-node--completed' : ''}`} style={{ left: node.x, top: node.y }}><span className="eyebrow">Outcome</span><strong>{node.name}</strong></div>)}
        </div>
      </div>
    </div>
  </div>
}
