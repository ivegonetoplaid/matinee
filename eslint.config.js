// ESLint for the page scripts: the recommended rules, plus the coding standards' ban on nested ternaries and
// their cyclomatic limit of 10.
import js from "@eslint/js";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["src/matinee/web/static/**/*.js"],
    languageOptions: { ecmaVersion: 2023, sourceType: "module", globals: globals.browser },
    rules: {
      "no-nested-ternary": "error",
      complexity: ["error", 10],
      "no-var": "error",
      "prefer-const": "error",
      eqeqeq: "error",
      "no-restricted-properties": [
        "error",
        { property: "innerHTML", message: "Build nodes with textContent; never assign innerHTML." },
        { property: "outerHTML", message: "Build nodes with textContent; never assign outerHTML." },
      ],
    },
  },
];
