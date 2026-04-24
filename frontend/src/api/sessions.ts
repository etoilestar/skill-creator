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
  requirement_score?: number
  status: string
  created_at: string
}

export const sessionsApi = {
  create: () => http.post<Session>('/sessions'),
  get: (id: string) => http.get<Session>(`/sessions/${id}`),
  sendMessage: (id: string, content: string, attachments?: string[]) =>
    http.post<Message>(`/sessions/${id}/messages`, { content, attachments }),
  getRequirement: (id: string) => http.get(`/sessions/${id}/requirement`),
  confirm: (id: string) => http.post(`/sessions/${id}/confirm`),
  uploadAttachment: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.post(`/sessions/${id}/attachments`, form, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
}
