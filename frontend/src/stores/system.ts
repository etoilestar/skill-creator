import { defineStore } from 'pinia'
import { ref } from 'vue'
import { kernelsApi, type Kernel } from '@/api/kernels'
import { configApi, type ModelConfig } from '@/api/config'
import { ElMessage } from 'element-plus'

export const useSystemStore = defineStore('system', () => {
  const kernels = ref<Kernel[]>([])
  const modelConfigs = ref<ModelConfig[]>([])
  const loadingKernels = ref(false)
  const loadingModels = ref(false)

  async function loadKernels() {
    loadingKernels.value = true
    try {
      const res = await kernelsApi.list()
      kernels.value = res.data
    } catch (e) {
      console.error(e)
    } finally {
      loadingKernels.value = false
    }
  }

  async function loadModels() {
    loadingModels.value = true
    try {
      const res = await configApi.listModels()
      modelConfigs.value = res.data
    } catch (e) {
      console.error(e)
    } finally {
      loadingModels.value = false
    }
  }

  async function createModel(data: Partial<ModelConfig>) {
    try {
      const res = await configApi.createModel(data)
      modelConfigs.value.push(res.data)
      ElMessage.success('Model created')
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  async function updateModel(id: string, data: Partial<ModelConfig>) {
    try {
      const res = await configApi.updateModel(id, data)
      const idx = modelConfigs.value.findIndex((m: ModelConfig) => m.id === id)
      if (idx !== -1) modelConfigs.value[idx] = res.data
      ElMessage.success('Model updated')
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  async function deleteModel(id: string) {
    try {
      await configApi.deleteModel(id)
      modelConfigs.value = modelConfigs.value.filter((m: ModelConfig) => m.id !== id)
      ElMessage.success('Model deleted')
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  async function activateModel(id: string) {
    try {
      await configApi.activateModel(id)
      modelConfigs.value.forEach((m: ModelConfig) => { m.is_active = m.id === id })
      ElMessage.success('Model activated')
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  async function testModel(id: string): Promise<{ latency: number; success: boolean }> {
    try {
      const res = await configApi.testModel(id)
      return res.data
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  return {
    kernels,
    modelConfigs,
    loadingKernels,
    loadingModels,
    loadKernels,
    loadModels,
    createModel,
    updateModel,
    deleteModel,
    activateModel,
    testModel,
  }
})
