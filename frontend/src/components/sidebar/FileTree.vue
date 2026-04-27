<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { filesApi } from '@/api/files'
import type { FileNode } from '@/api/files'
import { ElMessage, ElMessageBox } from 'element-plus'

const workspaceStore = useWorkspaceStore()
const fileTree = computed(() => workspaceStore.fileTree)
const currentTask = computed(() => workspaceStore.currentTask)

interface TreeNode {
  id: string
  label: string
  path: string
  type: 'file' | 'directory'
  children?: TreeNode[]
}

function toTreeNodes(nodes: FileNode[]): TreeNode[] {
  return nodes.map(n => ({
    id: n.path,
    label: n.name,
    path: n.path,
    type: n.type,
    children: n.children ? toTreeNodes(n.children) : undefined,
  }))
}

const treeData = computed(() => toTreeNodes(fileTree.value))

async function handleNodeClick(data: TreeNode) {
  if (data.type === 'file') {
    await workspaceStore.openFile(data.path)
  }
}

async function renameNode(node: TreeNode) {
  if (!currentTask.value) return
  const { value } = await ElMessageBox.prompt('新文件名：', '重命名', { inputValue: node.label })
  if (!value) return
  const dir = node.path.includes('/') ? node.path.substring(0, node.path.lastIndexOf('/')) : ''
  const newPath = dir ? `${dir}/${value}` : value
  try {
    await filesApi.rename(currentTask.value.id, node.path, newPath)
    await workspaceStore.loadFileTree()
    ElMessage.success('重命名成功')
  } catch {
    ElMessage.error('重命名失败')
  }
}

async function deleteNode(node: TreeNode) {
  if (!currentTask.value) return
  await ElMessageBox.confirm(`确认删除 "${node.label}"？`, '确认', { type: 'warning' })
  try {
    await filesApi.delete(currentTask.value.id, node.path)
    await workspaceStore.loadFileTree()
    ElMessage.success('删除成功')
  } catch {
    ElMessage.error('删除失败')
  }
}

async function newFile() {
  if (!currentTask.value) return
  const { value: name } = await ElMessageBox.prompt('文件名：', '新建文件', { inputValue: 'new_file.py' })
  if (!name) return
  try {
    await filesApi.write(currentTask.value.id, name, '')
    await workspaceStore.loadFileTree()
    await workspaceStore.openFile(name)
  } catch {
    ElMessage.error('创建文件失败')
  }
}

function downloadZip() {
  if (!currentTask.value) return
  filesApi.download(currentTask.value.id)
}
</script>

<template>
  <div class="file-tree">
    <div class="tree-toolbar">
      <el-button text size="small" @click="newFile" :disabled="!currentTask">
        <el-icon><Plus /></el-icon> 新建文件
      </el-button>
      <el-button text size="small" @click="workspaceStore.loadFileTree()" :disabled="!currentTask">
        <el-icon><Refresh /></el-icon>
      </el-button>
      <el-button text size="small" @click="downloadZip" :disabled="!currentTask?.workspace_path" title="下载 ZIP">
        <el-icon><Download /></el-icon>
      </el-button>
    </div>
    <div v-if="treeData.length === 0" class="tree-empty">
      <el-text v-if="currentTask" type="info" size="small">暂无文件</el-text>
      <el-text v-else type="info" size="small">请先选择任务</el-text>
    </div>
    <el-tree
      v-else
      :data="treeData"
      node-key="id"
      :expand-on-click-node="false"
      @node-click="(_: unknown, data: TreeNode) => handleNodeClick(data)"
      class="tree-component"
    >
      <template #default="{ data }">
        <el-dropdown trigger="contextmenu">
          <span class="tree-node">
            <el-icon class="node-icon">
              <Folder v-if="data.type === 'directory'" />
              <Document v-else />
            </el-icon>
            <span class="node-label">{{ data.label }}</span>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="renameNode(data)">重命名</el-dropdown-item>
              <el-dropdown-item @click="deleteNode(data)">删除</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>
    </el-tree>
  </div>
</template>

<style scoped>
.file-tree { height: 100%; overflow-y: auto; }
.tree-toolbar { display: flex; gap: 4px; padding: 4px 8px; border-bottom: 1px solid #eee; }
.tree-empty { padding: 16px; text-align: center; }
.tree-node { display: flex; align-items: center; gap: 4px; cursor: pointer; font-size: 13px; }
.node-icon { font-size: 14px; color: #909399; }
.node-label { user-select: none; }
.tree-component { padding: 4px; }
</style>
