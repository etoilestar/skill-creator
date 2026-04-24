import { defineStore } from 'pinia'
import { ref } from 'vue'
import { sessionsApi, type Session, type Message } from '@/api/sessions'
import { agentApi } from '@/api/agent'

export interface AgentMessage {
  role: 'user' | 'assistant' | 'status'
  content: string
  skillName?: string
  skillPath?: string
}

export const useChatStore = defineStore('chat', () => {
  const sessions = ref<Session[]>([])
  const currentSession = ref<Session | null>(null)
  const messages = ref<Message[]>([])
  const streaming = ref(false)
  const streamingContent = ref('')
  const requirementScore = ref(0)
  const chatMode = ref<'session' | 'agent'>('session')
  const agentMessages = ref<AgentMessage[]>([])
  const agentStreaming = ref(false)
  const agentStreamingContent = ref('')

  async function createSession() {
    try {
      const res = await sessionsApi.create()
      currentSession.value = res.data
      messages.value = res.data.messages || []
      requirementScore.value = res.data.requirement_score || 0
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  async function loadSession(id: string) {
    try {
      const res = await sessionsApi.get(id)
      currentSession.value = res.data
      messages.value = res.data.messages || []
      requirementScore.value = res.data.requirement_score || 0
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  async function sendMessage(content: string) {
    if (!currentSession.value) return
    streaming.value = true
    streamingContent.value = ''

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    }
    messages.value.push(userMsg)

    try {
      const response = await fetch(`/api/v1/sessions/${currentSession.value.id}/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      })
      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.type === 'text') {
                streamingContent.value += data.content
              } else if (data.type === 'done') {
                if (data.session) {
                  currentSession.value = data.session
                  messages.value = data.session.messages || []
                  requirementScore.value = data.session.requirement_score || 0
                } else {
                  const assistantMsg: Message = {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: streamingContent.value,
                    created_at: new Date().toISOString(),
                  }
                  messages.value.push(assistantMsg)
                }
                streamingContent.value = ''
              } else if (data.type === 'error') {
                console.error('Stream error:', data.message)
              }
            } catch { /* ignore */ }
          }
        }
      }
    } catch (e) {
      console.error(e)
      throw e
    } finally {
      streaming.value = false
    }
  }

  async function confirmCreation() {
    if (!currentSession.value) return
    try {
      const res = await sessionsApi.confirm(currentSession.value.id)
      return res.data
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  async function sendAgentMessage(content: string) {
    agentStreaming.value = true
    agentStreamingContent.value = ''
    agentMessages.value.push({ role: 'user', content })

    try {
      const result = await agentApi.stream(
        content,
        currentSession.value?.id,
        (chunk: string) => { agentStreamingContent.value += chunk },
        (status: string) => { agentMessages.value.push({ role: 'status', content: status }) }
      )
      agentMessages.value.push({
        role: 'assistant',
        content: agentStreamingContent.value,
        skillName: result.skill_name,
        skillPath: result.skill_path,
      })
      agentStreamingContent.value = ''
    } catch (e) {
      console.error(e)
      throw e
    } finally {
      agentStreaming.value = false
    }
  }

  return {
    sessions,
    currentSession,
    messages,
    streaming,
    streamingContent,
    requirementScore,
    chatMode,
    agentMessages,
    agentStreaming,
    agentStreamingContent,
    createSession,
    loadSession,
    sendMessage,
    confirmCreation,
    sendAgentMessage,
  }
})
