<script setup lang="ts">
import { ref } from 'vue'
import SessionChat from './SessionChat.vue'
import AgentChat from './AgentChat.vue'

const activeTab = ref('session')
</script>

<template>
  <div class="chat-panel">
    <el-tabs v-model="activeTab" class="chat-tabs">
      <el-tab-pane label="对话" name="session">
        <SessionChat />
      </el-tab-pane>
      <el-tab-pane label="智能体" name="agent">
        <AgentChat />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.chat-panel { width: 380px; flex-shrink: 0; border-left: 1px solid #e4e7ed; display: flex; flex-direction: column; overflow: hidden; }
.chat-tabs { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
:deep(.el-tabs__content) { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
:deep(.el-tab-pane) { height: 100%; display: flex; flex-direction: column; }
:deep(.el-tabs__header) { margin: 0; }
</style>
