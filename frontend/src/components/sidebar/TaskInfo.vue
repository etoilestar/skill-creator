<script setup lang="ts">
import { computed, ref } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { ElMessage } from 'element-plus'

const workspaceStore = useWorkspaceStore()
const task = computed(() => workspaceStore.currentTask)
const logs = computed(() => workspaceStore.taskLogs)
const showLogs = ref(false)
const retrying = ref(false)

type TagType = 'success' | 'warning' | 'danger' | 'info'

function getStatusType(status: string): TagType {
  const map: Record<string, TagType> = {
    pending: 'info', creating: 'warning', created: 'success', creation_failed: 'danger', iterating: 'warning',
    draft: 'info', testing: 'warning', passed: 'success', failed: 'danger', test_error: 'danger',
  }
  return map[status] || 'info'
}

async function retry() {
  retrying.value = true
  try {
    await workspaceStore.retryTask()
    ElMessage.success('Task retried')
  } catch {
    ElMessage.error('Failed to retry task')
  } finally {
    retrying.value = false
  }
}
</script>

<template>
  <div class="task-info" v-if="task">
    <div class="task-header">
    <div class="task-name">{{ task.skill_name || task.id }}</div>
      <el-tag :type="getStatusType(task.status)" size="small">{{ task.status }}</el-tag>
    </div>
    <p v-if="task.error_message" class="task-desc">{{ task.error_message }}</p>

    <div v-if="task.status === 'creating' || task.status === 'pending'" class="creating-state">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>{{ task.status === 'creating' ? 'Creating skill...' : 'Queued...' }}</span>
      <el-button link size="small" @click="showLogs = !showLogs">{{ showLogs ? 'Hide' : 'View' }} Logs</el-button>
      <div v-if="showLogs && logs" class="log-view"><pre>{{ logs }}</pre></div>
    </div>

    <div v-if="task.status === 'creation_failed'" class="failed-state">
      <el-button type="danger" size="small" :loading="retrying" @click="retry">
        <el-icon><RefreshRight /></el-icon> Retry
      </el-button>
      <el-button link size="small" @click="showLogs = !showLogs">{{ showLogs ? 'Hide' : 'View' }} Logs</el-button>
      <div v-if="showLogs && logs" class="log-view"><pre>{{ logs }}</pre></div>
    </div>

    <div v-if="task.status === 'created'" class="created-info">
      <el-text type="success" size="small">✅ Skill ready</el-text>
    </div>

    <div class="task-meta">
      <div class="meta-row">
        <span class="meta-label">Created:</span>
        <span>{{ new Date(task.created_at).toLocaleString() }}</span>
      </div>
    </div>
  </div>
  <div v-else class="no-task">
    <el-empty description="No task selected" :image-size="60" />
  </div>
</template>

<style scoped>
.task-info { padding: 12px; }
.task-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
.task-name { font-weight: 600; font-size: 14px; flex: 1; margin-right: 8px; word-break: break-word; }
.task-desc { color: #666; font-size: 12px; margin: 0 0 12px; }
.creating-state, .failed-state { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.log-view { width: 100%; max-height: 200px; overflow-y: auto; background: #1e1e1e; color: #d4d4d4; font-size: 11px; padding: 8px; border-radius: 4px; }
.log-view pre { margin: 0; white-space: pre-wrap; word-break: break-all; }
.created-info { margin-bottom: 8px; }
.task-meta { margin-top: 8px; border-top: 1px solid #eee; padding-top: 8px; }
.meta-row { display: flex; gap: 8px; font-size: 12px; color: #666; }
.meta-label { font-weight: 500; }
.no-task { padding: 20px 0; }
</style>
