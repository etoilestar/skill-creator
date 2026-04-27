import http from './http'

export interface ModelConfig {
  id: string
  name: string
  provider: string
  model_name: string
  api_key_configured?: boolean
  api_base_url?: string
  max_tokens?: number
  temperature?: number
  extra_params?: Record<string, unknown>
  is_active: boolean
  created_at: string
}

export interface ModelTestResult {
  success: boolean
  latency_ms?: number
  error?: string
  model_info?: Record<string, unknown>
}

export const configApi = {
  listModels: () => http.get<ModelConfig[]>('/config/models'),
  createModel: (data: Partial<ModelConfig> & { api_key?: string }) =>
    http.post<ModelConfig>('/config/models', data),
  updateModel: (id: string, data: Partial<ModelConfig> & { api_key?: string }) =>
    http.put<ModelConfig>(`/config/models/${id}`, data),
  deleteModel: (id: string) => http.delete<{ message: string }>(`/config/models/${id}`),
  activateModel: (id: string) =>
    http.post<{ message: string; config: ModelConfig }>(`/config/models/${id}/activate`),
  testModel: (id: string) => http.post<ModelTestResult>(`/config/models/${id}/test`),
  testModelInline: (data: {
    provider: string
    model_name: string
    api_key?: string
    api_base_url?: string
    max_tokens?: number
    temperature?: number
  }) => http.post<ModelTestResult>('/config/models/test', data),
}
