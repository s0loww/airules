// Loads the docgen core only after checking that its one npm dependency, `docx`, is
// installed. A static import of a missing package fails while Node links the module graph —
// before any of our code runs — with a stack trace and exit 1, which the scripts' contract
// reserves for findings. This turns it into a plain instruction and exit 2.
export async function loadDocgen(tool) {
  try {
    await import('docx');
  } catch (e) {
    if (e && (e.code === 'ERR_MODULE_NOT_FOUND' || e.code === 'MODULE_NOT_FOUND')) {
      console.error(`${tool}: the npm package "docx" is not installed — run "npm ci" in the skill's scripts/ directory (Node >= 18), then retry.`);
      process.exit(2);
    }
    throw e;
  }
  return import('./docgen.mjs');
}
