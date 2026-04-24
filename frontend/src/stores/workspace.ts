import { defineStore } from 'pinia'
import { ref } from 'vue'
import { tasksApi, type Task } from '@/api/tasks'
import { filesApi, type FileNode } from '@/api/files'

export interface OpenFile {
  path: string
  content: string
  savedContent: string
  language: string
}

function getLanguage(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase()
  const map: Record<string, string> = {
    py: 'python',
    md: 'markdown',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    js: 'javascript',
    ts: 'typescript',
    html: 'html',
    css: 'css',
    sh: 'shell',
    txt: 'plaintext',
  }
  return map[ext || ''] || 'plaintext'
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const tasks = ref<Task[]>([])
  const currentTask = ref<Task | null>(null)
  const fileTree = ref<FileNode[]>([])
  const openFiles = ref<OpenFile[]>([])
  const activeFile = ref<string | null>(null)
  const taskLogs = ref<string>('')
  const pollingInterval = ref<ReturnType<typeof setInterval> | null>(null)

  async function loadTasks() {
    try {
      const res = await tasksApi.list()
      tasks.value = res.data.tasks
    } catch (e) {
      console.error(e)
    }
  }

  async function selectTask(id: string) {
    stopPolling()
    try {
      const res = await tasksApi.get(id)
      currentTask.value = res.data
      if (res.data.status === 'CREATED' || res.data.status === 'ITERATING') {
        await loadFileTree()
      }
      if (res.data.status === 'CREATING' || res.data.status === 'PENDING') {
        startPolling()
      }
    } catch (e) {
      console.error(e)
    }
  }

  function startPolling() {
    if (pollingInterval.value) return
    pollingInterval.value = setInterval(async () => {
      if (!currentTask.value) return
      try {
        const res = await tasksApi.get(currentTask.value.id)
        const prev = currentTask.value.status
        currentTask.value = res.data
        // Keep task list in sync so the sidebar dropdown reflects status changes
        const idx = tasks.value.findIndex(t => t.id === res.data.id)
        if (idx !== -1) tasks.value[idx] = res.data
        if (res.data.status === 'CREATED' && prev !== 'CREATED') {
          await loadFileTree()
        }
        // Refresh file tree while Celery is actively writing files
        if (res.data.status === 'CREATING') {
          await loadFileTree()
        }
        await loadLogs()
        if (res.data.status === 'CREATED' || res.data.status === 'CREATION_FAILED') {
          stopPolling()
        }
      } catch (e) {
        console.error(e)
      }
    }, 3000)
  }

  function stopPolling() {
    if (pollingInterval.value) {
      clearInterval(pollingInterval.value)
      pollingInterval.value = null
    }
  }

  async function loadFileTree() {
    if (!currentTask.value) return
    try {
      const res = await filesApi.tree(currentTask.value.id)
      fileTree.value = res.data
    } catch (e) {
      console.error(e)
    }
  }

  async function openFile(path: string) {
    if (!currentTask.value) return
    const existing = openFiles.value.find(f => f.path === path)
    if (existing) {
      activeFile.value = path
      return
    }
    try {
      const res = await filesApi.read(currentTask.value.id, path)
      openFiles.value.push({
        path,
        content: res.data.content,
        savedContent: res.data.content,
        language: getLanguage(path),
      })
      activeFile.value = path
    } catch (e) {
      console.error(e)
    }
  }

  function closeFile(path: string) {
    const idx = openFiles.value.findIndex(f => f.path === path)
    if (idx !== -1) {
      openFiles.value.splice(idx, 1)
      if (activeFile.value === path) {
        activeFile.value = openFiles.value[Math.max(0, idx - 1)]?.path || null
      }
    }
  }

  function setActiveFile(path: string) {
    activeFile.value = path
  }

  async function saveFile(path: string) {
    if (!currentTask.value) return
    const file = openFiles.value.find(f => f.path === path)
    if (!file) return
    try {
      await filesApi.write(currentTask.value.id, path, file.content)
      file.savedContent = file.content
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  function updateFileContent(path: string, content: string) {
    const file = openFiles.value.find(f => f.path === path)
    if (file) file.content = content
  }

  async function loadLogs() {
    if (!currentTask.value) return
    try {
      const res = await tasksApi.getLogs(currentTask.value.id, { limit: 50 })
      taskLogs.value = res.data
        .map((log) => `[${log.created_at}] [${log.event_type}] ${log.message}`)
        .join('\n')
    } catch (e) {
      console.error(e)
    }
  }

  async function retryTask() {
    if (!currentTask.value) return
    try {
      const res = await tasksApi.retry(currentTask.value.id)
      currentTask.value = res.data.task
      startPolling()
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  return {
    tasks,
    currentTask,
    fileTree,
    openFiles,
    activeFile,
    taskLogs,
    pollingInterval,
    loadTasks,
    selectTask,
    startPolling,
    stopPolling,
    loadFileTree,
    openFile,
    closeFile,
    setActiveFile,
    saveFile,
    updateFileContent,
    loadLogs,
    retryTask,
  }
})
