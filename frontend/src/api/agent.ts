export const agentApi = {
  stream: async (
    message: string,
    sessionId?: string,
    onChunk?: (chunk: string) => void,
    onStatus?: (status: string) => void
  ): Promise<{ skill_name?: string; skill_path?: string }> => {
    const response = await fetch('/api/v1/agent/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId })
    })
    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let result: { skill_name?: string; skill_path?: string } = {}
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
            if (data.type === 'text') onChunk?.(data.content)
            else if (data.type === 'status') onStatus?.(data.message)
            else if (data.type === 'done') result = data
          } catch { /* ignore parse errors */ }
        }
      }
    }
    return result
  }
}
