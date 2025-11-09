import js from '@eslint/js';
import prettierConfig from 'eslint-config-prettier';
import importPlugin from 'eslint-plugin-import';
import promisePlugin from 'eslint-plugin-promise';
import securityPlugin from 'eslint-plugin-security';
import unicornPlugin from 'eslint-plugin-unicorn';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: ['dist/**', 'build/**', 'coverage/**', 'node_modules/**'],
  },
  {
    files: ['**/*.{js,ts,tsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    settings: {
      'import/resolver': {
        node: {
          extensions: ['.js', '.ts', '.tsx', '.json'],
        },
      },
    },
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  importPlugin.flatConfigs.recommended,
  promisePlugin.configs['flat/recommended'],
  securityPlugin.configs.recommended,
  {
    plugins: {
      unicorn: unicornPlugin,
    },
    rules: {
      // Import rules
      'import/no-cycle': 'error',
      'import/no-unused-modules': 'off', // Can be noisy
      'import/no-unresolved': 'off', // TypeScript handles this
      'import/order': 'off', // Can be fixed later with auto-fix
      
      // Promise rules
      'promise/always-return': 'error',
      'promise/no-return-wrap': 'error',
      'promise/param-names': 'error',
      'promise/catch-or-return': 'error',
      'promise/no-native': 'off',
      'promise/no-nesting': 'warn',
      'promise/no-promise-in-callback': 'warn',
      'promise/no-callback-in-promise': 'warn',
      
      // Security rules
      'security/detect-object-injection': 'off', // Too many false positives
      'security/detect-non-literal-regexp': 'warn',
      'security/detect-unsafe-regex': 'error',
      
      // Unicorn rules (selective)
      'unicorn/prefer-node-protocol': 'error',
      'unicorn/prefer-module': 'error',
      'unicorn/no-array-for-each': 'off', // forEach is fine
      'unicorn/prevent-abbreviations': 'off', // Too strict
      
      // Complexity rules (relaxed for existing code, will be tightened gradually)
      'complexity': 'off', // Will be enabled incrementally
      'max-lines-per-function': 'off', // Will be enabled incrementally
      'max-depth': ['warn', { max: 5 }],
      'max-nested-callbacks': ['warn', { max: 4 }],
      
      // Best practices
      'no-console': ['warn', { allow: ['warn', 'error', 'info', 'debug'] }],
      'no-template-curly-in-string': 'error',
      'require-atomic-updates': 'error',
    },
  },
  {
    files: ['tests/**/*.{js,ts,tsx}'],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
    rules: {
      'no-console': 'off',
      'max-lines-per-function': 'off',
    },
  },
  prettierConfig,
);
