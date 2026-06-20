// Cross-surface remote control: lets flow steer the on-printer FilaMind screen. The agent
// connection is opened lazily on first use (init), then kept warm — so flow never holds a second
// websocket unless the operator actually opens the Remote Control page.

import { defineStore } from 'pinia'
import { ref } from 'vue'

import { CommandSender } from '@/core/remote/command-sender'
import type { RemoteView, RemoteMessageLevel } from '@/core/remote/commands'

export const useRemoteControlStore = defineStore('remoteControl', () => {
  const ready = ref(false)
  let sender: CommandSender | null = null

  /** Idempotent: open the agent command bus (call when the Remote Control surface mounts). */
  function init(): void {
    if (sender) return
    sender = new CommandSender({
      client_name: 'FilaMind flow',
      version: typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'unknown',
      url: 'https://filamind.app',
      onReadyChange: (r) => {
        ready.value = r
      },
    })
    sender.start()
  }

  const navigate = (view: RemoteView): Promise<void> => sender?.navigate(view) ?? Promise.resolve()
  const message = (level: RemoteMessageLevel, text: string): Promise<void> =>
    sender?.message(level, text) ?? Promise.resolve()
  const locate = (): Promise<void> => sender?.locate() ?? Promise.resolve()

  return { ready, init, navigate, message, locate }
})
