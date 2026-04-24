<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useSystemStore } from '@/stores/system'

const systemStore = useSystemStore()
const runningKernels = computed(() => systemStore.kernels.filter((k: { status: string }) => k.status === 'running').length)

onMounted(() => systemStore.loadKernels())
</script>

<template>
  <el-popover trigger="click" width="280" placement="bottom-end">
    <template #reference>
      <el-badge :value="runningKernels" :hidden="runningKernels === 0" type="success">
        <el-button text circle>
          <el-icon size="16"><Monitor /></el-icon>
        </el-button>
      </el-badge>
    </template>
    <div class="kernel-popover">
      <div class="kernel-header">Kernels ({{ systemStore.kernels.length }})</div>
      <div v-if="systemStore.kernels.length === 0" class="kernel-empty">No kernels</div>
      <div v-for="kernel in systemStore.kernels" :key="kernel.id" class="kernel-item">
        <div class="kernel-info">
          <span class="kernel-name">{{ kernel.name }}</span>
          <span class="kernel-lang">{{ kernel.language }}</span>
        </div>
        <el-tag :type="kernel.status === 'running' ? 'success' : 'info'" size="small">{{ kernel.status }}</el-tag>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.kernel-popover { padding: 4px 0; }
.kernel-header { font-weight: 600; padding: 0 0 8px; border-bottom: 1px solid #eee; margin-bottom: 8px; }
.kernel-empty { color: #999; text-align: center; padding: 8px; }
.kernel-item { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; }
.kernel-info { display: flex; flex-direction: column; }
.kernel-name { font-size: 13px; }
.kernel-lang { font-size: 11px; color: #999; }
</style>
