<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useSystemStore } from '@/stores/system'
import type { ModelConfig } from '@/api/config'
import { ElMessage } from 'element-plus'

defineProps<{ visible: boolean }>()
const emit = defineEmits<{ 'update:visible': [v: boolean] }>()

const systemStore = useSystemStore()
const showDialog = ref(false)
const editingModel = ref<(Partial<ModelConfig> & { api_key?: string }) | null>(null)
const isEdit = ref(false)
const testResults = ref<Record<string, { latency_ms?: number; success: boolean } | null>>({})

const emptyForm = () => ({
  name: '', provider: '', model_name: '', api_key: '', api_base_url: '', is_active: false as const,
})

function openAdd() {
  isEdit.value = false
  editingModel.value = emptyForm()
  showDialog.value = true
}

function openEdit(model: ModelConfig) {
  isEdit.value = true
  editingModel.value = { ...model }
  showDialog.value = true
}

async function saveModel() {
  if (!editingModel.value) return
  try {
    if (isEdit.value && editingModel.value.id) {
      await systemStore.updateModel(editingModel.value.id, editingModel.value)
    } else {
      await systemStore.createModel(editingModel.value)
    }
    showDialog.value = false
  } catch {
    ElMessage.error('Failed to save model')
  }
}

async function deleteModel(id: string) {
  try { await systemStore.deleteModel(id) } catch { ElMessage.error('Failed to delete model') }
}

async function activateModel(id: string) {
  try { await systemStore.activateModel(id) } catch { ElMessage.error('Failed to activate model') }
}

async function testModel(id: string) {
  testResults.value[id] = null
  try {
    const result = await systemStore.testModel(id)
    testResults.value[id] = result
    if (result.success) ElMessage.success(`Connected! Latency: ${result.latency_ms ?? '?'}ms`)
    else ElMessage.error(`Connection failed: ${result.error || ''}`)
  } catch {
    ElMessage.error('Test failed')
  }
}

onMounted(() => systemStore.loadModels())
</script>

<template>
  <el-drawer :model-value="visible" title="Settings" size="520px" @update:model-value="emit('update:visible', $event)">
    <div class="settings-section">
      <div class="section-header">
        <h3>Model Configurations</h3>
        <el-button type="primary" size="small" @click="openAdd">Add Model</el-button>
      </div>
      <el-table :data="systemStore.modelConfigs" size="small" v-loading="systemStore.loadingModels">
        <el-table-column prop="name" label="Name" />
        <el-table-column prop="provider" label="Provider" />
        <el-table-column prop="model_name" label="Model" />
        <el-table-column label="Active" width="60">
          <template #default="{ row }">
            <el-icon v-if="row.is_active" color="#67c23a"><StarFilled /></el-icon>
            <el-icon v-else color="#ddd"><Star /></el-icon>
          </template>
        </el-table-column>
        <el-table-column label="Actions" width="160">
          <template #default="{ row }">
            <el-button link size="small" @click="openEdit(row)">Edit</el-button>
            <el-button link size="small" @click="activateModel(row.id)">Activate</el-button>
            <el-button link size="small" @click="testModel(row.id)">Test</el-button>
            <el-button link size="small" type="danger" @click="deleteModel(row.id)">Del</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="showDialog" :title="isEdit ? 'Edit Model' : 'Add Model'" width="460px" append-to-body>
      <el-form :model="editingModel" label-width="100px" v-if="editingModel">
        <el-form-item label="Name" required><el-input v-model="editingModel.name" /></el-form-item>
        <el-form-item label="Provider">
          <el-select v-model="editingModel.provider" placeholder="Select provider" style="width: 100%">
            <el-option label="OpenAI" value="openai" />
            <el-option label="Azure OpenAI" value="azure" />
            <el-option label="Local (OpenAI compat)" value="local_openai_compat" />
          </el-select>
        </el-form-item>
        <el-form-item label="Model Name"><el-input v-model="editingModel.model_name" placeholder="gpt-4o, etc." /></el-form-item>
        <el-form-item label="API Key"><el-input v-model="editingModel.api_key" type="password" show-password :placeholder="isEdit ? 'Leave blank to keep current' : ''" /></el-form-item>
        <el-form-item label="Base URL"><el-input v-model="editingModel.api_base_url" placeholder="https://api.openai.com/v1" /></el-form-item>
        <el-form-item label="Max Tokens"><el-input-number v-model="editingModel.max_tokens" :min="1" :max="128000" /></el-form-item>
        <el-form-item label="Temperature"><el-slider v-model="editingModel.temperature" :min="0" :max="2" :step="0.1" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">Cancel</el-button>
        <el-button type="primary" @click="saveModel">Save</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<style scoped>
.settings-section { padding: 0 4px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; }
</style>
