<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { useChatStore } from '@/stores/chat'
import { ElMessage } from 'element-plus'

const chatStore = useChatStore()

const inputText = ref('')
const messagesEl = ref<HTMLElement | null>(null)
const sending = ref(false)

const agentMessages = computed(() => chatStore.agentMessages)
const agentStreaming = computed(() => chatStore.agentStreaming)
const agentStreamContent = computed(() => chatStore.agentStreamingContent)

async function send() {
  const text = inputText.value.trim()
  if (!text || sending.value) return
  inputText.value = ''
  sending.value = true
  try {
    await chatStore.sendAgentMessage(text)
    await scrollToBottom()
  } catch {
    ElMessage.error('Agent request failed')
  } finally {
    sending.value = false
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

watch(agentMessages, scrollToBottom, { deep: true })
watch(agentStreamContent, scrollToBottom)
</script>

<template>
  <div class="agent-chat">
    <div class="messages" ref="messagesEl">
      <div v-for="(msg, idx) in agentMessages" :key="idx" class="message" :class="msg.role">
        <div v-if="msg.role === 'status'" class="status-msg">
          <el-icon><InfoFilled /></el-icon>
          {{ msg.content }}
        </div>
        <div v-else class="message-bubble">
          <div class="message-content">{{ msg.content }}</div>
          <div v-if="msg.skillName" class="skill-card">
            <el-icon><Cpu /></el-icon>
            <strong>{{ msg.skillName }}</strong>
            <el-tag type="success" size="small">Matched</el-tag>
          </div>
        </div>
      </div>
      <div v-if="agentStreaming && agentStreamContent" class="message assistant">
        <div class="message-bubble streaming">
          <div class="message-content">{{ agentStreamContent }}<span class="cursor">▋</span></div>
        </div>
      </div>
      <div v-if="agentMessages.length === 0 && !agentStreaming" class="chat-empty">
        <el-text type="info" size="small">Ask the agent to find or execute a skill...</el-text>
      </div>
    </div>

    <div class="input-area">
      <el-input v-model="inputText" type="textarea" :rows="3" placeholder="Ask the agent..." :disabled="sending || agentStreaming" @keydown.enter.exact.prevent="send" />
      <div class="input-actions">
        <el-button type="primary" size="small" :loading="sending || agentStreaming" @click="send">Send</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-chat { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 12px; }
.message { display: flex; }
.message.user { justify-content: flex-end; }
.message.assistant { justify-content: flex-start; }
.message.status { justify-content: center; }
.status-msg { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #909399; padding: 4px 12px; background: #f5f7fa; border-radius: 20px; }
.message-bubble { max-width: 80%; padding: 8px 12px; border-radius: 12px; font-size: 13px; }
.message.user .message-bubble { background: #409eff; color: #fff; border-bottom-right-radius: 4px; }
.message.assistant .message-bubble { background: #f0f0f0; color: #333; border-bottom-left-radius: 4px; }
.message-bubble.streaming { background: #f0f0f0; }
.message-content { word-break: break-word; white-space: pre-wrap; }
.skill-card { display: flex; align-items: center; gap: 6px; margin-top: 8px; padding: 6px 10px; background: #ecf5ff; border-radius: 6px; border: 1px solid #b3d8ff; }
.cursor { animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }
.chat-empty { text-align: center; padding: 20px; }
.input-area { padding: 8px 12px; border-top: 1px solid #eee; flex-shrink: 0; }
.input-actions { display: flex; justify-content: flex-end; margin-top: 6px; }
</style>
