<script setup lang="ts">
// Navigation is intentionally minimal in the scaffold. Add links/routes as
// features land.
const nav = [{ id: 'dashboard', label: 'Dashboard', icon: '▣' }] as const
</script>

<template>
  <aside
    class="hidden w-60 shrink-0 flex-col gap-6 border-r-3 border-ink bg-brand-yellow p-4 md:flex"
  >
    <div class="nb-card bg-surface px-3 py-4">
      <p class="font-display text-2xl font-bold leading-none">FilaMind</p>
      <p class="font-mono text-xs tracking-tight">FLOW · klipper panel</p>
    </div>

    <nav class="flex flex-col gap-2">
      <a v-for="item in nav" :key="item.id" class="nb-btn justify-start bg-surface" href="#">
        <span aria-hidden="true">{{ item.icon }}</span>
        {{ item.label }}
      </a>
    </nav>

    <p class="mt-auto font-mono text-[10px] leading-tight opacity-70">
      Extensible · Neo-Brutalist<br />Moonraker · Klipper
    </p>
  </aside>
</template>
