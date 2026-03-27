import globals from "globals";
import importPlugin from "eslint-plugin-import";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "dist-node", "storybook-static"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [tseslint.configs.recommended],
    plugins: {
      import: importPlugin,
    },
    languageOptions: {
      globals: globals.browser,
      ecmaVersion: 2022,
      parserOptions: {
        // TODO: remove once typescript-eslint ships TS 6 support (PR #12124)
        warnOnUnsupportedTypeScriptVersion: false,
      },
    },
    settings: {
      "import/resolver": {
        typescript: true,
      },
    },
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_" },
      ],
      "import/no-cycle": "error",
      "max-lines": ["error", { max: 400, skipBlankLines: true, skipComments: true }],
    },
  },
);
