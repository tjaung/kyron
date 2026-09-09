import { createContext } from 'react'
import type { AuthSession, Practice } from './types'

export interface AuthState {
  practice: Practice | null
  session: AuthSession | null
  loading: boolean
  error: string
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)
