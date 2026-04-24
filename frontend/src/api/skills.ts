import http from './http'

export interface Skill {
  task_id?: string
  name: string
  description: string
  skill_path?: string
  score?: number
}

export interface SkillDetail {
  task_id: string
  skill_name: string
  skill_md_content: string
  frontmatter: { name: string; description: string }
  workspace_path: string
}

export interface SkillListResponse {
  skills: Skill[]
  total: number
}

export interface SkillSearchResponse {
  query: string
  results: Skill[]
  total_indexed: number
}

export const skillsApi = {
  list: (limit?: number) =>
    http.get<SkillListResponse>('/skills', { params: limit ? { limit } : undefined }),
  search: (q: string, top_k?: number) =>
    http.get<SkillSearchResponse>('/skills/search', { params: { q, ...(top_k ? { top_k } : {}) } }),
  get: (taskId: string) => http.get<SkillDetail>(`/skills/${taskId}`),
  delete: (taskId: string) => http.delete<{ message: string; task_id: string }>(`/skills/${taskId}`),
  import: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.post('/skills/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  }
}
