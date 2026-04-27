<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { useWorkspaceStore } from '@/stores/workspace'
import type { OpenFile } from '@/stores/workspace'
import SkillMdPreview from './SkillMdPreview.vue'
import { ElMessage } from 'element-plus'

const workspaceStore = useWorkspaceStore()
const openFiles = computed(() => workspaceStore.openFiles)
const activeFile = computed(() => workspaceStore.activeFile)
const previewMode = ref(false)

const activeFileObj = computed(() => openFiles.value.find((f: OpenFile) => f.path === activeFile.value) || null)
const isSkillMd = computed(() => activeFile.value?.endsWith('SKILL.md') || activeFile.value?.endsWith('skill.md'))

function handleTabChange(path: string) {
  workspaceStore.setActiveFile(path)
  previewMode.value = false
}

function handleTabClose(path: string) {
  workspaceStore.closeFile(path)
}

function handleEditorChange(value: string | undefined) {
  if (activeFile.value && value !== undefined) {
    workspaceStore.updateFileContent(activeFile.value, value)
  }
}

async function saveCurrentFile() {
  if (!activeFile.value) return
  try {
    await workspaceStore.saveFile(activeFile.value)
    ElMessage.success('已保存')
  } catch {
    ElMessage.error('保存失败')
  }
}

function handleKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    saveCurrentFile()
  }
}

onMounted(() => document.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', handleKeydown))

const isUnsaved = (path: string) => {
  const f = openFiles.value.find((f: OpenFile) => f.path === path)
  return f ? f.content !== f.savedContent : false
}
</script>

<template>
  <div class="editor-panel">
    <div v-if="openFiles.length === 0" class="editor-empty">
      <el-empty description="请从左侧文件树选择文件" />
    </div>
    <template v-else>
      <div class="editor-tabs">
        <div
          v-for="file in openFiles"
          :key="file.path"
          class="tab-item"
          :class="{ active: file.path === activeFile }"
          @click="handleTabChange(file.path)"
        >
          <span class="tab-label">
            {{ file.path.split('/').pop() }}
            <span v-if="isUnsaved(file.path)" class="unsaved-dot">●</span>
          </span>
          <el-button text size="small" class="tab-close" @click.stop="handleTabClose(file.path)">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
      </div>

      <div class="editor-toolbar">
        <el-button size="small" type="primary" @click="saveCurrentFile" :disabled="!activeFile">
          <el-icon><DocumentChecked /></el-icon> 保存
        </el-button>
        <template v-if="isSkillMd">
          <el-button size="small" :type="!previewMode ? 'primary' : 'default'" @click="previewMode = false">编辑</el-button>
          <el-button size="small" :type="previewMode ? 'primary' : 'default'" @click="previewMode = true">预览</el-button>
        </template>
      </div>

      <div class="editor-body">
        <SkillMdPreview v-if="isSkillMd && previewMode && activeFileObj" :content="activeFileObj.content" />
        <VueMonacoEditor
          v-else-if="activeFileObj"
          :value="activeFileObj.content"
          :language="activeFileObj.language"
          theme="vs-dark"
          :options="{
            fontSize: 14,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            automaticLayout: true,
            wordWrap: 'on',
          }"
          @change="handleEditorChange"
          style="height: 100%"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.editor-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; background: #1e1e1e; }
.editor-empty { flex: 1; display: flex; align-items: center; justify-content: center; background: #252526; }
.editor-tabs { display: flex; background: #252526; border-bottom: 1px solid #3c3c3c; overflow-x: auto; flex-shrink: 0; }
.tab-item { display: flex; align-items: center; padding: 0 8px 0 12px; min-width: 120px; max-width: 200px; height: 36px; cursor: pointer; color: #ccc; font-size: 13px; border-right: 1px solid #3c3c3c; transition: background 0.15s; flex-shrink: 0; }
.tab-item:hover { background: #2d2d2d; }
.tab-item.active { background: #1e1e1e; color: #fff; border-bottom: 2px solid #0e90d2; }
.tab-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.unsaved-dot { color: #e2c08d; margin-left: 4px; }
.tab-close { color: #ccc; padding: 0; margin-left: 4px; }
.editor-toolbar { display: flex; gap: 8px; padding: 6px 10px; background: #2d2d2d; border-bottom: 1px solid #3c3c3c; flex-shrink: 0; }
.editor-body { flex: 1; overflow: hidden; }
</style>
