<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps<{ content: string }>()

const frontmatterContent = computed(() => {
  const match = props.content.match(/^---\n([\s\S]*?)\n---/)
  return match ? match[1] : null
})

const bodyContent = computed(() => {
  const body = props.content.replace(/^---\n[\s\S]*?\n---\n?/, '')
  return String(marked.parse(body))
})
</script>

<template>
  <div class="skill-md-preview">
    <div v-if="frontmatterContent" class="frontmatter-section">
      <div class="frontmatter-label">YAML 元数据</div>
      <pre class="frontmatter-content">{{ frontmatterContent }}</pre>
    </div>
    <div class="markdown-body" v-html="bodyContent" />
  </div>
</template>

<style scoped>
.skill-md-preview { padding: 16px; overflow-y: auto; height: 100%; background: #fff; }
.frontmatter-section { background: #f0f4ff; border: 1px solid #c0ccff; border-radius: 6px; padding: 12px; margin-bottom: 16px; }
.frontmatter-label { font-size: 11px; font-weight: 600; color: #5470c6; text-transform: uppercase; margin-bottom: 6px; }
.frontmatter-content { margin: 0; font-size: 12px; font-family: monospace; color: #333; white-space: pre-wrap; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { border-bottom: 1px solid #eee; padding-bottom: 0.3em; margin-top: 1.5em; }
.markdown-body :deep(code) { background: #f5f5f5; padding: 2px 4px; border-radius: 3px; font-size: 0.9em; }
.markdown-body :deep(pre) { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; overflow-x: auto; }
.markdown-body :deep(pre code) { background: none; padding: 0; color: inherit; }
</style>
