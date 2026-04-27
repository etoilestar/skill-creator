<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from '@/components/layout/AppHeader.vue'
import SidebarPanel from '@/components/sidebar/SidebarPanel.vue'
import EditorPanel from '@/components/editor/EditorPanel.vue'
import ChatPanel from '@/components/chat/ChatPanel.vue'
import { useWorkspaceStore } from '@/stores/workspace'

const route = useRoute()
const workspaceStore = useWorkspaceStore()

onMounted(async () => {
  await workspaceStore.loadTasks()
  const taskId = route.params.taskId as string
  if (taskId) {
    await workspaceStore.selectTask(taskId)
  }
})

onUnmounted(() => {
  workspaceStore.stopPolling()
})
</script>

<template>
  <div class="workbench">
    <AppHeader />
    <div class="workbench-body">
      <SidebarPanel />
      <EditorPanel />
      <ChatPanel />
    </div>
  </div>
</template>

<style scoped>
.workbench {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}
.workbench-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}
</style>
