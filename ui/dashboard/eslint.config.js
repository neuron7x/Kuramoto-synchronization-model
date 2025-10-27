import js from '@eslint/js';
import globals from 'globals';
import prettierRecommended from 'eslint-plugin-prettier/recommended';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: ['dist/**', 'build/**', 'coverage/**'],
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
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  prettierRecommended,
  {
    files: ['tests/**/*.{js,ts,tsx}'],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
);
