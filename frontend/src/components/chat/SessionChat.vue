<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useWorkspaceStore } from '@/stores/workspace'
import { ElMessage, ElMessageBox } from 'element-plus'
import { sessionsApi } from '@/api/sessions'

const chatStore = useChatStore()
const workspaceStore = useWorkspaceStore()

const inputText = ref('')
const messagesEl = ref<HTMLElement | null>(null)
const sending = ref(false)
const confirming = ref(false)

const score = computed(() => chatStore.requirementScore)
const messages = computed(() => chatStore.messages)
const streaming = computed(() => chatStore.streaming)
const streamContent = computed(() => chatStore.streamingContent)

async function init() {
  if (!chatStore.currentSession) {
    try { await chatStore.createSession() } catch (e) { console.error(e) }
  }
}

async function send() {
  const text = inputText.value.trim()
  if (!text || sending.value) return
  inputText.value = ''
  sending.value = true
  try {
    await chatStore.sendMessage(text)
    await scrollToBottom()
  } catch {
    ElMessage.error('消息发送失败')
  } finally {
    sending.value = false
  }
}

async function newSession() {
  try {
    await chatStore.createSession()
  } catch { ElMessage.error('创建对话失败') }
}

async function clearSession() {
  try {
    await ElMessageBox.confirm('清空当前对话并重置需求？此操作不可撤销。', '清空对话', {
      confirmButtonText: '确认清空',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await chatStore.clearSession()
    ElMessage.success('对话已清空')
  } catch (e: unknown) {
    if (e !== 'cancel') ElMessage.error('清空对话失败')
  }
}

function handleSessionCommand(cmd: string) {
  if (cmd === 'new') newSession()
  else if (cmd === 'clear') clearSession()
}

async function confirm() {
  confirming.value = true
  try {
    const result = await chatStore.confirmCreation()
    ElMessage.success('已开始创建 Skill！')
    if (result?.id) {
      await workspaceStore.loadTasks()
      await workspaceStore.selectTask(result.id)
    }
  } catch {
    ElMessage.error('启动创建失败')
  } finally {
    confirming.value = false
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

function handleAttachment() {
  if (!chatStore.currentSession) return
  const input = document.createElement('input')
  input.type = 'file'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    try {
      await sessionsApi.uploadAttachment(chatStore.currentSession!.id, file)
      ElMessage.success('附件上传成功')
    } catch {
      ElMessage.error('上传失败')
    }
  }
  input.click()
}

watch(messages, scrollToBottom, { deep: true })
watch(streamContent, scrollToBottom)

init()
</script>

<template>
  <div class="session-chat">
    <div class="chat-header">
      <el-progress
        :percentage="score"
        :format="(p: number) => `完整度: ${p}`"
        :status="score >= 80 ? 'success' : undefined"
        size="small"
        style="flex: 1"
      />
      <el-dropdown size="small" @command="handleSessionCommand">
        <el-button text size="small">管理<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="new">新建对话</el-dropdown-item>
            <el-dropdown-item command="clear" divided>清空当前对话</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <div class="messages" ref="messagesEl">
      <div v-for="msg in messages" :key="msg.id" class="message" :class="msg.role">
        <div class="message-bubble">
          <div class="message-content">{{ msg.content }}</div>
          <div class="message-time">{{ new Date(msg.created_at).toLocaleTimeString() }}</div>
        </div>
      </div>
      <div v-if="streaming && streamContent" class="message assistant">
        <div class="message-bubble streaming">
          <div class="message-content">{{ streamContent }}<span class="cursor">▋</span></div>
        </div>
      </div>
      <div v-if="messages.length === 0 && !streaming" class="chat-empty">
        <el-text type="info" size="small">请描述您想创建的 Skill...</el-text>
      </div>
    </div>

    <div v-if="score >= 80" class="confirm-bar">
      <el-button type="success" size="small" :loading="confirming" @click="confirm" style="width: 100%">
        ✅ 开始创建 Skill
      </el-button>
    </div>

    <div class="input-area">
      <el-input v-model="inputText" type="textarea" :rows="3" placeholder="请描述您想创建的 Skill..." :disabled="sending || streaming" @keydown.enter.exact.prevent="send" />
      <div class="input-actions">
        <el-button text size="small" @click="handleAttachment"><el-icon><Paperclip /></el-icon></el-button>
        <el-button type="primary" size="small" :loading="sending || streaming" @click="send">发送</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.session-chat { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.chat-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid #eee; flex-shrink: 0; }
.messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; }
.message { display: flex; }
.message.user { justify-content: flex-end; }
.message.assistant { justify-content: flex-start; }
.message-bubble { max-width: 80%; padding: 8px 12px; border-radius: 12px; font-size: 13px; }
.message.user .message-bubble { background: #409eff; color: #fff; border-bottom-right-radius: 4px; }
.message.assistant .message-bubble { background: #f0f0f0; color: #333; border-bottom-left-radius: 4px; }
.message-bubble.streaming { background: #f0f0f0; }
.message-content { word-break: break-word; white-space: pre-wrap; }
.message-time { font-size: 10px; opacity: 0.6; margin-top: 4px; text-align: right; }
.cursor { animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }
.chat-empty { text-align: center; padding: 20px; }
.confirm-bar { padding: 8px 12px; border-top: 1px solid #eee; flex-shrink: 0; }
.input-area { padding: 8px 12px; border-top: 1px solid #eee; flex-shrink: 0; }
.input-actions { display: flex; justify-content: space-between; margin-top: 6px; }
</style>
