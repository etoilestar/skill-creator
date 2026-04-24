import http from './http'

export interface Kernel {
  id: string
  name: string
  status: string
  language: string
}

export const kernelsApi = {
  list: () => http.get<Kernel[]>('/kernels'),
}
