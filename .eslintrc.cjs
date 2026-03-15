module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  ignorePatterns: ['dist', 'node_modules', 'storybook-static', '*.cjs'],
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
  ],
  rules: {
    '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
  },
};
