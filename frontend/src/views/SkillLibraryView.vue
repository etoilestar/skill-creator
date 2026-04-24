<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '@/components/layout/AppHeader.vue'
import { skillsApi, type Skill } from '@/api/skills'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const skills = ref<Skill[]>([])
const loading = ref(false)
const searchQuery = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null

async function loadSkills() {
  loading.value = true
  try {
    const res = await skillsApi.list()
    skills.value = res.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function searchSkills(q: string) {
  if (!q.trim()) {
    await loadSkills()
    return
  }
  loading.value = true
  try {
    const res = await skillsApi.search(q)
    skills.value = res.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function onSearchInput(val: string) {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => searchSkills(val), 300)
}

async function deleteSkill(taskId: string) {
  await ElMessageBox.confirm('Delete this skill?', 'Confirm', { type: 'warning' })
  try {
    await skillsApi.delete(taskId)
    skills.value = skills.value.filter((s: Skill) => s.task_id !== taskId)
    ElMessage.success('Skill deleted')
  } catch {
    ElMessage.error('Failed to delete skill')
  }
}

function openSkill(taskId: string) {
  router.push(`/workspace/${taskId}`)
}

function importZip() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.zip'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    try {
      await skillsApi.import(file)
      ElMessage.success('Skill imported')
      await loadSkills()
    } catch {
      ElMessage.error('Failed to import skill')
    }
  }
  input.click()
}

function getStatusType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    CREATED: 'success',
    CREATING: 'warning',
    PENDING: 'info',
    CREATION_FAILED: 'danger',
    ITERATING: 'warning',
  }
  return map[status] || 'info'
}

onMounted(loadSkills)
</script>

<template>
  <div class="skill-library">
    <AppHeader />
    <div class="library-content">
      <div class="library-toolbar">
        <el-input
          v-model="searchQuery"
          placeholder="Search skills..."
          clearable
          style="width: 300px"
          @input="onSearchInput"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" @click="importZip">
          <el-icon><Upload /></el-icon>
          Import ZIP
        </el-button>
      </div>

      <div v-loading="loading" class="skill-grid">
        <el-empty v-if="!loading && skills.length === 0" description="No skills found" />
        <el-card
          v-for="skill in skills"
          :key="skill.task_id"
          class="skill-card"
          shadow="hover"
        >
          <template #header>
            <div class="card-header">
              <span class="skill-name">{{ skill.name }}</span>
              <el-tag :type="getStatusType(skill.status)" size="small">{{ skill.status }}</el-tag>
            </div>
          </template>
          <p class="skill-desc">{{ skill.description }}</p>
          <div v-if="skill.tags?.length" class="skill-tags">
            <el-tag v-for="tag in skill.tags" :key="tag" size="small" class="tag-item">{{ tag }}</el-tag>
          </div>
          <div class="skill-meta">
            <span>{{ new Date(skill.created_at).toLocaleDateString() }}</span>
          </div>
          <div class="skill-actions">
            <el-button size="small" type="primary" @click="openSkill(skill.task_id)">Open</el-button>
            <el-button size="small" type="danger" @click="deleteSkill(skill.task_id)">Delete</el-button>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<style scoped>
.skill-library { display: flex; flex-direction: column; height: 100vh; }
.library-content { flex: 1; padding: 20px; overflow-y: auto; }
.library-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.skill-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.skill-card { transition: transform 0.2s; }
.skill-card:hover { transform: translateY(-2px); }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.skill-name { font-weight: 600; font-size: 15px; }
.skill-desc { color: #666; font-size: 13px; margin: 8px 0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.skill-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.tag-item { margin: 0; }
.skill-meta { color: #999; font-size: 12px; margin-bottom: 12px; }
.skill-actions { display: flex; gap: 8px; }
</style>
