<script setup lang="ts">
import { onMounted } from 'vue'
import TouchShell from './components/TouchShell.vue'
import { useSessionStore } from './core/store/session'

const sessionStore = useSessionStore()
onMounted(() => {
  sessionStore.start().catch((e) => console.error('session start failed', e))
})
</script>

<template>
  <TouchShell />
</template>
