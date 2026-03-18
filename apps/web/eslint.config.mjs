import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "dist-node", "storybook-static"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [tseslint.configs.recommended],
    languageOptions: {
      globals: globals.browser,
      ecmaVersion: 2022,
    },
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_" },
      ],
    },
  },
);
