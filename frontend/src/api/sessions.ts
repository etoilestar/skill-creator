import http from './http'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface Session {
  id: string
  messages: Message[]
  completeness_score: number
  requirement_spec?: Record<string, unknown>
  status: string
  created_at: string
}

export const sessionsApi = {
  create: (message: string) => http.post<Session>('/sessions', { message }),
  get: (id: string) => http.get<Session>(`/sessions/${id}`),
  sendMessage: (id: string, message: string) =>
    http.post<{ ai_reply: string; session: Session }>(`/sessions/${id}/messages`, { message }),
  getRequirement: (id: string) =>
    http.get<{ session_id: string; requirement_spec: Record<string, unknown>; completeness_score: number; can_create: boolean }>(`/sessions/${id}/requirement`),
  confirm: (id: string) =>
    http.post<{ message: string; task: { id: string; status: string; skill_name?: string } }>(`/sessions/${id}/confirm`),
  uploadAttachment: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.post(`/sessions/${id}/attachments`, form, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
}
