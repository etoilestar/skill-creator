<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import TaskInfo from './TaskInfo.vue'
import FileTree from './FileTree.vue'
import TestPanel from './TestPanel.vue'

const workspaceStore = useWorkspaceStore()
const tasks = computed(() => workspaceStore.tasks)
const currentTaskId = computed(() => workspaceStore.currentTask?.id || '')

async function selectTask(id: string) {
  await workspaceStore.selectTask(id)
}
</script>

<template>
  <div class="sidebar-panel">
    <div class="task-selector">
      <el-select :model-value="currentTaskId" placeholder="Select task..." size="small" style="width: 100%" @change="selectTask">
        <el-option v-for="task in tasks" :key="task.id" :label="task.name || task.id" :value="task.id" />
      </el-select>
    </div>
    <el-tabs class="sidebar-tabs">
      <el-tab-pane label="Task"><TaskInfo /></el-tab-pane>
      <el-tab-pane label="Files"><FileTree /></el-tab-pane>
      <el-tab-pane label="Tests"><TestPanel /></el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.sidebar-panel { width: 240px; flex-shrink: 0; border-right: 1px solid #e4e7ed; display: flex; flex-direction: column; overflow: hidden; background: #fafafa; }
.task-selector { padding: 8px; border-bottom: 1px solid #e4e7ed; }
.sidebar-tabs { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
:deep(.el-tabs__content) { flex: 1; overflow-y: auto; padding: 0; }
:deep(.el-tab-pane) { height: 100%; }
:deep(.el-tabs__header) { margin: 0; }
</style>
