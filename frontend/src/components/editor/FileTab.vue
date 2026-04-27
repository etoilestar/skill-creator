<script setup lang="ts">
defineProps<{ path: string; active: boolean; unsaved: boolean }>()
defineEmits<{ click: []; close: [] }>()
</script>
<template>
  <div class="file-tab" :class="{ active, unsaved }" @click="$emit('click')">
    <span>{{ path.split('/').pop() }}</span>
    <span v-if="unsaved" class="dot">●</span>
    <button @click.stop="$emit('close')">×</button>
  </div>
</template>
<style scoped>
.file-tab { display: flex; align-items: center; gap: 4px; padding: 4px 8px; cursor: pointer; }
.file-tab.active { font-weight: 600; }
.dot { color: orange; }
</style>
