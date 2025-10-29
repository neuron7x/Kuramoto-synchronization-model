module.exports = {
  root: true,
  parser: "@typescript-eslint/parser",
  plugins: ["@typescript-eslint", "import", "security"],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:import/recommended",
    "plugin:security/recommended"
  ],
  rules: {
    "no-console": ["error", { allow: ["warn", "error"] }],
    "import/order": [
      "error",
      { alphabetize: { order: "asc" }, "newlines-between": "always" }
    ]
  }
};
