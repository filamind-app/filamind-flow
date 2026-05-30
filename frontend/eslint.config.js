import pluginVue from 'eslint-plugin-vue'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

// Flat config (ESLint 9). Prettier owns formatting; `skipFormatting` disables
// any stylistic rules that would conflict with it.
export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,vue}'],
  },
  {
    name: 'app/files-to-ignore',
    ignores: ['dist/**', 'node_modules/**', 'coverage/**'],
  },
  pluginVue.configs['flat/recommended'],
  vueTsConfigs.recommended,
  skipFormatting,
  {
    // The root component is conventionally single-word.
    name: 'app/root-component-exception',
    files: ['src/App.vue'],
    rules: {
      'vue/multi-word-component-names': 'off',
    },
  },
)
