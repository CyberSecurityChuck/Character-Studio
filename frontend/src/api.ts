export interface Preferences {
  studio_name: string
  revision: number
}

export interface Provider {
  id: string
  name: string
  status: 'planned' | 'unverified' | 'disabled' | 'available'
  description: string
  pricing: string
}

export interface Bootstrap {
  preferences: Preferences
  session_token: string
  phase: number
  schema_revision: string
  data_directory: string
  paid_operations_enabled: boolean
  providers: Provider[]
  max_upload_bytes: number
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
  }
}

export async function request<T>(path: string, options?: RequestInit, fallback = 'Check the name, age category and other fields before saving.'): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 60_000)
  try {
    const response = await fetch(path, { ...options, signal: controller.signal })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new ApiError(
        typeof body.detail === 'string' ? body.detail : fallback,
        response.status,
      )
    }
    return await response.json() as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError('Connection interrupted. Reload to check whether your change was saved before retrying.', 0)
  } finally {
    window.clearTimeout(timeout)
  }
}

export const getBootstrap = () => request<Bootstrap>('/api/bootstrap')

export const savePreferences = (preferences: Preferences, token: string) =>
  request<Preferences>('/api/preferences', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Studio-Token': token },
    body: JSON.stringify(preferences),
  })

// JSON writes carry the session token; the fallback message covers field-level validation errors.
export const send = <T>(path: string, method: string, token: string, body?: unknown) => request<T>(path, {
  method, headers: { 'X-Studio-Token': token, 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
}, 'Some entries are missing or too long. Check them and try again.')
