<script setup lang="ts">
import { computed, ref } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { ElMessage, ElMessageBox } from 'element-plus'
import TaskInfo from './TaskInfo.vue'
import FileTree from './FileTree.vue'
import TestPanel from './TestPanel.vue'

const workspaceStore = useWorkspaceStore()
const tasks = computed(() => workspaceStore.tasks)
const currentTaskId = computed(() => workspaceStore.currentTask?.id || '')

// context menu state
const contextMenu = ref<{ visible: boolean; x: number; y: number; taskId: string }>({
  visible: false, x: 0, y: 0, taskId: '',
})

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿', pending: '排队中', creating: '创建中', created: '已创建',
  creation_failed: '创建失败', iterating: '迭代中', testing: '测试中',
  passed: '已通过', failed: '未通过', test_error: '测试异常',
}

function statusLabel(s: string) { return STATUS_LABELS[s] || s }
function statusType(s: string): 'success' | 'warning' | 'danger' | 'info' {
  const m: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    draft: 'info', pending: 'info', creating: 'warning', created: 'success',
    creation_failed: 'danger', iterating: 'warning', testing: 'warning',
    passed: 'success', failed: 'danger', test_error: 'danger',
  }
  return m[s] || 'info'
}

async function selectTask(id: string) {
  await workspaceStore.selectTask(id)
}

function onContextMenu(e: MouseEvent, taskId: string) {
  e.preventDefault()
  contextMenu.value = { visible: true, x: e.clientX, y: e.clientY, taskId }
}

function closeContextMenu() {
  contextMenu.value.visible = false
}

async function deleteTask() {
  const id = contextMenu.value.taskId
  closeContextMenu()
  try {
    await ElMessageBox.confirm('确认删除该任务？此操作不可恢复。', '删除任务', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await workspaceStore.deleteTask(id)
    ElMessage.success('任务已删除')
  } catch (e: unknown) {
    if (e !== 'cancel') ElMessage.error('删除任务失败')
  }
}
</script>

<template>
  <div class="sidebar-panel" @click="closeContextMenu">
    <div class="task-list-header">任务列表</div>
    <div class="task-list">
      <div
        v-for="task in tasks"
        :key="task.id"
        class="task-item"
        :class="{ active: task.id === currentTaskId }"
        @click.stop="selectTask(task.id)"
        @contextmenu.stop="onContextMenu($event, task.id)"
      >
        <span class="task-label" :title="task.skill_name || task.id">{{ task.skill_name || task.id }}</span>
        <el-tag :type="statusType(task.status)" size="small" class="task-status-tag">
          {{ statusLabel(task.status) }}
        </el-tag>
      </div>
      <div v-if="tasks.length === 0" class="task-list-empty">暂无任务</div>
    </div>

    <!-- 右键上下文菜单 -->
    <teleport to="body">
      <div
        v-if="contextMenu.visible"
        class="ctx-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <div class="ctx-menu-item danger" @click="deleteTask">
          <el-icon><Delete /></el-icon> 删除任务
        </div>
      </div>
    </teleport>

    <el-tabs class="sidebar-tabs">
      <el-tab-pane label="任务"><TaskInfo /></el-tab-pane>
      <el-tab-pane label="文件"><FileTree /></el-tab-pane>
      <el-tab-pane label="测试"><TestPanel /></el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.sidebar-panel { width: 240px; flex-shrink: 0; border-right: 1px solid #e4e7ed; display: flex; flex-direction: column; overflow: hidden; background: #fafafa; }
.task-list-header { padding: 6px 10px; font-size: 12px; font-weight: 600; color: #909399; border-bottom: 1px solid #e4e7ed; background: #f5f7fa; }
.task-list { max-height: 180px; overflow-y: auto; border-bottom: 1px solid #e4e7ed; flex-shrink: 0; }
.task-item { display: flex; align-items: center; justify-content: space-between; gap: 4px; padding: 6px 10px; cursor: pointer; font-size: 13px; transition: background 0.15s; user-select: none; }
.task-item:hover { background: #ecf5ff; }
.task-item.active { background: #d9ecff; font-weight: 600; }
.task-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-status-tag { flex-shrink: 0; }
.task-list-empty { padding: 12px 10px; text-align: center; color: #c0c4cc; font-size: 12px; }
.sidebar-tabs { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
:deep(.el-tabs__content) { flex: 1; overflow-y: auto; padding: 0; }
:deep(.el-tab-pane) { height: 100%; }
:deep(.el-tabs__header) { margin: 0; }

/* Right-click context menu */
.ctx-menu { position: fixed; z-index: 9999; background: #fff; border: 1px solid #e4e7ed; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.12); padding: 4px 0; min-width: 130px; }
.ctx-menu-item { display: flex; align-items: center; gap: 6px; padding: 8px 14px; font-size: 13px; cursor: pointer; transition: background 0.1s; }
.ctx-menu-item:hover { background: #f5f7fa; }
.ctx-menu-item.danger { color: #f56c6c; }
.ctx-menu-item.danger:hover { background: #fef0f0; }
</style>
