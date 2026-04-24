import http from './http'

export interface Skill {
  task_id: string
  name: string
  description: string
  status: string
  created_at: string
  tags?: string[]
}

export const skillsApi = {
  list: () => http.get<Skill[]>('/skills'),
  search: (q: string) => http.get<Skill[]>('/skills/search', { params: { q } }),
  get: (taskId: string) => http.get<Skill>(`/skills/${taskId}`),
  delete: (taskId: string) => http.delete(`/skills/${taskId}`),
  import: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.post('/skills/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  }
}
