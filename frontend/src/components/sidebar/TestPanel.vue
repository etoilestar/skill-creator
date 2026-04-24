<script setup lang="ts">
import { ref, computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

const workspaceStore = useWorkspaceStore()
const currentTask = computed(() => workspaceStore.currentTask)
const canTest = computed(() => ['created', 'iterating'].includes(currentTask.value?.status || ''))

interface TestRun {
  id: string
  status: string
  passed: number
  total: number
  created_at: string
}

const tests = ref<TestRun[]>([])
const running = ref(false)
const loading = ref(false)
const selectedTest = ref<string | null>(null)
const testLogs = ref<Record<string, string>>({})

async function runTests() {
  if (!currentTask.value) return
  running.value = true
  try {
    await http.post(`/tasks/${currentTask.value.id}/tests`)
    ElMessage.success('Tests triggered')
    await loadTests()
  } catch {
    ElMessage.error('Failed to run tests')
  } finally {
    running.value = false
  }
}

async function loadTests() {
  if (!currentTask.value) return
  loading.value = true
  try {
    const res = await http.get<TestRun[]>(`/tasks/${currentTask.value.id}/tests`)
    tests.value = res.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function loadTestLogs(testId: string) {
  if (!currentTask.value) return
  try {
    const res = await http.get<{ logs: string }>(`/tasks/${currentTask.value.id}/tests/${testId}/logs`)
    testLogs.value[testId] = res.data.logs
  } catch (e) {
    console.error(e)
  }
}

function toggleTest(testId: string) {
  if (selectedTest.value === testId) {
    selectedTest.value = null
  } else {
    selectedTest.value = testId
    if (!testLogs.value[testId]) loadTestLogs(testId)
  }
}

function getPassRate(test: TestRun): number {
  if (!test.total) return 0
  return Math.round((test.passed / test.total) * 100)
}

function getProgressStatus(status: string): 'success' | 'exception' | undefined {
  if (status === 'passed') return 'success'
  if (status === 'failed') return 'exception'
  return undefined
}

function getStatusType(status: string): 'success' | 'danger' | 'warning' | 'info' {
  if (status === 'passed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}
</script>

<template>
  <div class="test-panel">
    <div class="test-toolbar">
      <el-button type="primary" size="small" :disabled="!canTest" :loading="running" @click="runTests">
        <el-icon><CaretRight /></el-icon> Run Tests
      </el-button>
      <el-button text size="small" @click="loadTests" :disabled="!currentTask">
        <el-icon><Refresh /></el-icon>
      </el-button>
    </div>
    <div v-if="!currentTask" class="test-empty">Select a task</div>
    <div v-else-if="!canTest" class="test-empty">
      <el-text type="info" size="small">Tests available when task is CREATED</el-text>
    </div>
    <div v-else-if="tests.length === 0" class="test-empty">
      <el-text type="info" size="small">No test runs yet</el-text>
    </div>
    <div v-else class="test-list" v-loading="loading">
      <div v-for="test in tests" :key="test.id" class="test-item" @click="toggleTest(test.id)">
        <div class="test-header">
          <el-tag :type="getStatusType(test.status)" size="small">{{ test.status }}</el-tag>
          <span class="test-date">{{ new Date(test.created_at).toLocaleTimeString() }}</span>
        </div>
        <el-progress
          :percentage="getPassRate(test)"
          :status="getProgressStatus(test.status)"
          size="small"
          :format="() => `${test.passed}/${test.total}`"
        />
        <el-collapse-transition>
          <div v-if="selectedTest === test.id" class="test-logs">
            <pre>{{ testLogs[test.id] || 'Loading...' }}</pre>
          </div>
        </el-collapse-transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.test-panel { height: 100%; overflow-y: auto; }
.test-toolbar { display: flex; gap: 4px; padding: 8px; border-bottom: 1px solid #eee; }
.test-empty { padding: 16px; text-align: center; color: #999; font-size: 13px; }
.test-list { padding: 8px; }
.test-item { border: 1px solid #eee; border-radius: 6px; padding: 8px; margin-bottom: 8px; cursor: pointer; transition: background 0.1s; }
.test-item:hover { background: #f5f7fa; }
.test-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.test-date { font-size: 11px; color: #999; }
.test-logs { margin-top: 8px; background: #1e1e1e; color: #d4d4d4; border-radius: 4px; padding: 8px; max-height: 150px; overflow-y: auto; }
.test-logs pre { margin: 0; font-size: 11px; white-space: pre-wrap; word-break: break-all; }
</style>
