import http from './http'

export interface FileNode {
  name: string
  path: string
  type: 'file' | 'directory'
  children?: FileNode[]
}

export const filesApi = {
  tree: (taskId: string) => http.get<FileNode[]>(`/tasks/${taskId}/files`),
  read: (taskId: string, path: string) => http.get<{ content: string }>(`/tasks/${taskId}/files/${path}`),
  write: (taskId: string, path: string, content: string) => http.put(`/tasks/${taskId}/files/${path}`, { content }),
  delete: (taskId: string, path: string) => http.delete(`/tasks/${taskId}/files/${path}`),
  rename: (taskId: string, oldPath: string, newPath: string) => http.post(`/tasks/${taskId}/files/rename`, { old_path: oldPath, new_path: newPath }),
  download: (taskId: string) => {
    const a = document.createElement('a')
    a.href = `/api/v1/tasks/${taskId}/download`
    a.download = ''
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  },
}
