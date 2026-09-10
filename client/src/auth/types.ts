export interface Practice {
  practice_id: string
  name: string
  slug: string
}

export interface AuthSession {
  practice: Practice
  provider: {
    provider_id: string
    first_name: string
    last_name: string
    username: string
  }
}
