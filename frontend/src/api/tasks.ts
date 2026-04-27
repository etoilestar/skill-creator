import http from './http'

export interface Task {
  id: string
  skill_name: string
  status: 'pending' | 'creating' | 'created' | 'creation_failed' | 'iterating' | 'draft' | 'testing' | 'passed' | 'failed' | 'test_error'
  created_at: string
  updated_at: string
  workspace_path?: string
  session_id?: string
  error_message?: string
  requirement_spec?: Record<string, unknown>
}

export interface TaskLog {
  id: string
  task_id: string
  event_type: string
  event_data: Record<string, unknown>
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
  create: (skillName?: string) =>
    http.post<Task>('/tasks', { skill_name: skillName }),
  get: (id: string) => http.get<Task>(`/tasks/${id}`),
  delete: (id: string) => http.delete(`/tasks/${id}`),
  getLogs: (id: string, params?: { event_type?: string; limit?: number }) =>
    http.get<TaskLog[]>(`/tasks/${id}/logs`, { params }),
  retry: (id: string) => http.post<{ message: string; task: Task }>(`/tasks/${id}/retry`),
}
