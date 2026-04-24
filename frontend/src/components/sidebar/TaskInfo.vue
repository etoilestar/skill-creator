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

const statusLabels: Record<string, string> = {
  pending: '排队中', creating: '创建中', created: '已创建', creation_failed: '创建失败',
  iterating: '迭代中', draft: '草稿', testing: '测试中', passed: '已通过',
  failed: '未通过', test_error: '测试异常',
}

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
    ElMessage.success('任务已重试')
  } catch {
    ElMessage.error('任务重试失败')
  } finally {
    retrying.value = false
  }
}
</script>

<template>
  <div class="task-info" v-if="task">
    <div class="task-header">
    <div class="task-name">{{ task.skill_name || task.id }}</div>
      <el-tag :type="getStatusType(task.status)" size="small">{{ statusLabels[task.status] || task.status }}</el-tag>
    </div>
    <p v-if="task.error_message" class="task-desc">{{ task.error_message }}</p>

    <div v-if="task.status === 'creating' || task.status === 'pending'" class="creating-state">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>{{ task.status === 'creating' ? '正在创建 Skill...' : '排队中...' }}</span>
      <el-button link size="small" @click="showLogs = !showLogs">{{ showLogs ? '隐藏' : '查看' }}日志</el-button>
      <div v-if="showLogs && logs" class="log-view"><pre>{{ logs }}</pre></div>
    </div>

    <div v-if="task.status === 'creation_failed'" class="failed-state">
      <el-button type="danger" size="small" :loading="retrying" @click="retry">
        <el-icon><RefreshRight /></el-icon> 重试
      </el-button>
      <el-button link size="small" @click="showLogs = !showLogs">{{ showLogs ? '隐藏' : '查看' }}日志</el-button>
      <div v-if="showLogs && logs" class="log-view"><pre>{{ logs }}</pre></div>
    </div>

    <div v-if="task.status === 'created'" class="created-info">
      <el-text type="success" size="small">✅ Skill 已就绪</el-text>
    </div>

    <div class="task-meta">
      <div class="meta-row">
        <span class="meta-label">创建时间：</span>
        <span>{{ new Date(task.created_at).toLocaleString('zh-CN') }}</span>
      </div>
    </div>
  </div>
  <div v-else class="no-task">
    <el-empty description="未选择任务" :image-size="60" />
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
