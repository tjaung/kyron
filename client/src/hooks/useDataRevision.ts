import { useSyncExternalStore } from 'react'
let revision = 0
const listeners = new Set<() => void>()
export function refreshData() {
  revision += 1
  listeners.forEach(listener => listener())
}
function subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } }
export function useDataRevision() { return useSyncExternalStore(subscribe, () => revision) }
