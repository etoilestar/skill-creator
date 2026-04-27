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

const testingInline = ref(false)
const inlineTestResult = ref<{ success: boolean; latency_ms?: number; error?: string } | null>(null)

async function testInDialog() {
  if (!editingModel.value) return
  testingInline.value = true
  inlineTestResult.value = null
  try {
    const result = await systemStore.testModelInline({
      provider: editingModel.value.provider || '',
      model_name: editingModel.value.model_name || '',
      api_key: editingModel.value.api_key,
      api_base_url: editingModel.value.api_base_url,
      max_tokens: editingModel.value.max_tokens,
      temperature: editingModel.value.temperature,
    })
    inlineTestResult.value = result
    if (result.success) ElMessage.success(`连接成功！延迟: ${result.latency_ms ?? '?'}ms`)
    else ElMessage.error(`连接失败: ${result.error || ''}`)
  } catch {
    ElMessage.error('测试请求失败')
  } finally {
    testingInline.value = false
  }
}

function openAdd() {
  isEdit.value = false
  editingModel.value = emptyForm()
  inlineTestResult.value = null
  showDialog.value = true
}

function openEdit(model: ModelConfig) {
  isEdit.value = true
  editingModel.value = { ...model }
  inlineTestResult.value = null
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
    ElMessage.error('模型保存失败')
  }
}

async function deleteModel(id: string) {
  try { await systemStore.deleteModel(id) } catch { ElMessage.error('模型删除失败') }
}

async function activateModel(id: string) {
  try { await systemStore.activateModel(id) } catch { ElMessage.error('激活失败') }
}

async function testModel(id: string) {
  testResults.value[id] = null
  try {
    const result = await systemStore.testModel(id)
    testResults.value[id] = result
    if (result.success) ElMessage.success(`连接成功！延迟: ${result.latency_ms ?? '?'}ms`)
    else ElMessage.error(`连接失败: ${result.error || ''}`)
  } catch {
    ElMessage.error('测试失败')
  }
}

onMounted(() => systemStore.loadModels())
</script>

<template>
  <el-drawer :model-value="visible" title="设置" size="520px" @update:model-value="emit('update:visible', $event)">
    <div class="settings-section">
      <div class="section-header">
        <h3>模型配置</h3>
        <el-button type="primary" size="small" @click="openAdd">添加模型</el-button>
      </div>
      <el-table :data="systemStore.modelConfigs" size="small" v-loading="systemStore.loadingModels">
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="provider" label="提供商" />
        <el-table-column prop="model_name" label="模型" />
        <el-table-column label="启用" width="60">
          <template #default="{ row }">
            <el-icon v-if="row.is_active" color="#67c23a"><StarFilled /></el-icon>
            <el-icon v-else color="#ddd"><Star /></el-icon>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link size="small" @click="activateModel(row.id)">激活</el-button>
            <el-button link size="small" @click="testModel(row.id)">测试</el-button>
            <el-button link size="small" type="danger" @click="deleteModel(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="showDialog" :title="isEdit ? '编辑模型' : '添加模型'" width="460px" append-to-body :close-on-click-modal="false">
      <el-form :model="editingModel" label-width="100px" v-if="editingModel">
        <el-form-item label="名称" required><el-input v-model="editingModel.name" /></el-form-item>
        <el-form-item label="提供商">
          <el-select v-model="editingModel.provider" placeholder="选择提供商" style="width: 100%">
            <el-option label="OpenAI" value="openai" />
            <el-option label="Azure OpenAI" value="azure" />
            <el-option label="本地兼容接口" value="local_openai_compat" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型名称"><el-input v-model="editingModel.model_name" placeholder="gpt-4o 等" /></el-form-item>
        <el-form-item label="API 密钥"><el-input v-model="editingModel.api_key" type="password" show-password :placeholder="isEdit ? '留空保持不变' : ''" /></el-form-item>
        <el-form-item label="接口地址"><el-input v-model="editingModel.api_base_url" placeholder="https://api.openai.com/v1" /></el-form-item>
        <el-form-item label="最大 Token 数"><el-input-number v-model="editingModel.max_tokens" :min="1" :max="128000" /></el-form-item>
        <el-form-item label="随机性"><el-slider v-model="editingModel.temperature" :min="0" :max="2" :step="0.1" /></el-form-item>
        <el-form-item v-if="inlineTestResult">
          <el-text :type="inlineTestResult.success ? 'success' : 'danger'" size="small">
            {{ inlineTestResult.success ? `✅ 连接成功，延迟 ${inlineTestResult.latency_ms ?? '?'}ms` : `❌ 连接失败：${inlineTestResult.error || '未知错误'}` }}
          </el-text>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button :loading="testingInline" @click="testInDialog">测试连接</el-button>
        <el-button type="primary" @click="saveModel">保存</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<style scoped>
.settings-section { padding: 0 4px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; }
</style>
