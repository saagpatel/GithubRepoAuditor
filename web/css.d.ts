// TypeScript 6 checks side-effect imports by default (noUncheckedSideEffectImports).
// Next bundles global CSS itself, so declare the module shape for tsc.
declare module "*.css";
