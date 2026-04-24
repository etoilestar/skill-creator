import http from './http'

export interface ModelConfig {
  id: string
  name: string
  provider: string
  model: string
  api_key?: string
  base_url?: string
  is_active: boolean
  created_at: string
}

export const configApi = {
  listModels: () => http.get<ModelConfig[]>('/config/models'),
  createModel: (data: Partial<ModelConfig>) => http.post<ModelConfig>('/config/models', data),
  updateModel: (id: string, data: Partial<ModelConfig>) => http.put<ModelConfig>(`/config/models/${id}`, data),
  deleteModel: (id: string) => http.delete(`/config/models/${id}`),
  activateModel: (id: string) => http.post(`/config/models/${id}/activate`),
  testModel: (id: string) => http.post<{ latency: number; success: boolean }>(`/config/models/${id}/test`),
}
