import { defineStore } from 'pinia'
import { ref } from 'vue'
import { sessionsApi, type Session, type Message } from '@/api/sessions'
import { agentApi } from '@/api/agent'

/** Normalize raw backend message objects (which may use `timestamp` instead of `id`/`created_at`) into the frontend Message shape. */
function normalizeMessages(raw: any[]): Message[] {
  return (raw || []).map((m: any, idx: number) => ({
    // Prefer timestamp as a stable key to avoid unnecessary DOM reconstruction
    id: m.timestamp || m.id || String(idx),
    role: m.role,
    content: m.content,
    created_at: m.created_at || m.timestamp || new Date().toISOString(),
  }))
}

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

  async function createSession(initialMessage?: string) {
    try {
      const res = await sessionsApi.create(initialMessage || '我想创建一个新的 Skill')
      currentSession.value = res.data
      messages.value = normalizeMessages(res.data.messages)
      requirementScore.value = res.data.completeness_score || 0
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  async function clearSession() {
    try {
      await createSession()
    } catch (e) {
      console.error(e)
      throw e
    }
  }

  async function loadSession(id: string) {
    try {
      const res = await sessionsApi.get(id)
      currentSession.value = res.data
      messages.value = normalizeMessages(res.data.messages)
      requirementScore.value = res.data.completeness_score || 0
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
        body: JSON.stringify({ message: content })
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
                const accumulated = streamingContent.value
                if (data.session) {
                  currentSession.value = data.session
                  const normalized = normalizeMessages(data.session.messages)
                  // Fallback: if the session doesn't include a valid assistant reply, add the
                  // accumulated streaming content so the message is never lost.
                  const lastMsg = normalized[normalized.length - 1]
                  if ((!lastMsg || lastMsg.role !== 'assistant' || !lastMsg.content) && accumulated) {
                    normalized.push({
                      id: (Date.now() + 1).toString(),
                      role: 'assistant',
                      content: accumulated,
                      created_at: new Date().toISOString(),
                    })
                  }
                  messages.value = normalized
                  requirementScore.value = data.session.completeness_score || 0
                } else {
                  if (accumulated) {
                    messages.value.push({
                      id: (Date.now() + 1).toString(),
                      role: 'assistant',
                      content: accumulated,
                      created_at: new Date().toISOString(),
                    })
                  }
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
      // Safety net: if the stream ended without a done event being successfully parsed
      // (e.g. network interruption, backend exception, malformed JSON), persist any
      // accumulated streaming content so the reply is never silently lost.
      if (streamingContent.value) {
        messages.value.push({
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: streamingContent.value,
          created_at: new Date().toISOString(),
        })
        streamingContent.value = ''
      }
      streaming.value = false
    }
  }

  async function confirmCreation() {
    if (!currentSession.value) return
    try {
      const res = await sessionsApi.confirm(currentSession.value.id)
      return res.data.task
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
    clearSession,
    loadSession,
    sendMessage,
    confirmCreation,
    sendAgentMessage,
  }
})
