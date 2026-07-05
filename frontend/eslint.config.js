import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

const noRestrictedImports = (patterns) => [
  'error',
  {
    patterns: patterns.map((pattern) => ({
      group: [pattern],
      message: 'Frontend の依存方向ルールに反しています。',
    })),
  },
]

export default tseslint.config(
  { ignores: ['dist'] },
  js.configs.recommended,
  {
    files: ['*.cjs'],
    languageOptions: {
      globals: globals.node,
    },
  },
  {
    files: ['playwright.config.ts', 'e2e/**/*.ts'],
    languageOptions: {
      globals: globals.node,
    },
  },
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
    },
  },
  {
    files: ['src/components/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': noRestrictedImports([
        '../api/*',
        '../../api/*',
        '@/api/*',
        'src/api/*',
      ]),
    },
  },
  {
    files: ['src/lib/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': noRestrictedImports(['react', 'react/*']),
    },
  },
  {
    files: ['src/api/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': noRestrictedImports([
        '../pages/*',
        '../../pages/*',
        '../components/*',
        '../../components/*',
        '@/pages/*',
        '@/components/*',
        'src/pages/*',
        'src/components/*',
      ]),
    },
  },
)
