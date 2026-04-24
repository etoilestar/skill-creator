import http from './http'

export interface Task {
  id: string
  skill_name: string
  status: 'PENDING' | 'CREATING' | 'CREATED' | 'CREATION_FAILED' | 'ITERATING'
  created_at: string
  updated_at: string
  workspace_path?: string
  error_message?: string
  requirement_spec?: Record<string, unknown>
}

export interface TaskLog {
  id: string
  task_id: string
  event_type: string
  message: string
  created_at: string
}

export interface TaskListResponse {
  tasks: Task[]
  total: number
  page: number
  per_page: number
  pages: number
}

export const tasksApi = {
  list: (params?: { status?: string; page?: number; per_page?: number }) =>
    http.get<TaskListResponse>('/tasks', { params }),
  get: (id: string) => http.get<Task>(`/tasks/${id}`),
  getLogs: (id: string, params?: { event_type?: string; limit?: number }) =>
    http.get<TaskLog[]>(`/tasks/${id}/logs`, { params }),
  retry: (id: string) => http.post<{ message: string; task: Task }>(`/tasks/${id}/retry`),
}
