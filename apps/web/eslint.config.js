const next = require('eslint-config-next')
const prettierFlat = require('eslint-config-prettier/flat')
const prettierPlugin = require('eslint-plugin-prettier')

module.exports = [
  ...next,
  prettierFlat,
  {
    files: ['**/*.ts', '**/*.tsx'],
    // `@typescript-eslint` is already registered by eslint-config-next; the
    // 8.58.2 plugin rejects re-registration with
    // "Cannot redefine plugin" so we only add our local overrides here.
    plugins: { prettier: prettierPlugin },
    rules: {
      'prettier/prettier': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/explicit-function-return-type': 'off',
      '@typescript-eslint/explicit-module-boundary-types': 'off',
      'react/react-in-jsx-scope': 'off',
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    },
  },
  {
    files: ['**/*.js', '**/*.cjs', '**/*.mjs'],
    plugins: { prettier: prettierPlugin },
    rules: {
      'prettier/prettier': 'error',
    },
  },
  {
    files: ['scripts/**'],
    rules: {
      'no-console': 'off',
    },
  },
  {
    ignores: [
      '.next/**',
      'next-env.d.ts',
      'out/**',
      'build/**',
      'dist/**',
      'playwright-report/**',
      'test-results/**',
      'coverage/**',
    ],
  },
]
