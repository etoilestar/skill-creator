<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import SettingsDrawer from './SettingsDrawer.vue'
import KernelStatus from './KernelStatus.vue'

const router = useRouter()
const showSettings = ref(false)

function navigate(key: string) {
  if (key === 'workbench') router.push('/')
  else if (key === 'library') router.push('/skills')
}
</script>

<template>
  <header class="app-header">
    <div class="header-left">
      <div class="logo">🔧 Skill Creator</div>
      <el-menu mode="horizontal" :ellipsis="false" class="nav-menu" @select="navigate">
        <el-menu-item index="workbench">Workbench</el-menu-item>
        <el-menu-item index="library">Library</el-menu-item>
      </el-menu>
    </div>
    <div class="header-right">
      <KernelStatus />
      <el-button circle text @click="showSettings = true">
        <el-icon size="18"><Setting /></el-icon>
      </el-button>
    </div>
    <SettingsDrawer v-model:visible="showSettings" />
  </header>
</template>

<style scoped>
.app-header { display: flex; align-items: center; justify-content: space-between; height: 56px; padding: 0 16px; border-bottom: 1px solid #e4e7ed; background: #fff; flex-shrink: 0; z-index: 100; }
.header-left { display: flex; align-items: center; gap: 16px; }
.logo { font-size: 18px; font-weight: 700; color: #409eff; white-space: nowrap; }
.nav-menu { border-bottom: none !important; }
.header-right { display: flex; align-items: center; gap: 12px; }
</style>
