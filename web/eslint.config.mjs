import nextVitals from "eslint-config-next/core-web-vitals";
import { defineConfig, globalIgnores } from "eslint/config";

export default defineConfig([
	...nextVitals,
	globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);
