import http from './http'

export interface Task {
  id: string
  name: string
  description: string
  status: 'PENDING' | 'CREATING' | 'CREATED' | 'CREATION_FAILED' | 'ITERATING'
  created_at: string
  updated_at: string
  requirement?: string
}

export const tasksApi = {
  list: () => http.get<Task[]>('/tasks'),
  get: (id: string) => http.get<Task>(`/tasks/${id}`),
  getLogs: (id: string) => http.get<{ logs: string }>(`/tasks/${id}/logs`),
  retry: (id: string) => http.post<Task>(`/tasks/${id}/retry`),
}
