/** Built-in evidence contracts. Domain-specific formats belong to separate validators. */
const passed = () => ({ status: 'passed' })
const failed = reason => ({ status: 'failed', reason })
const unknown = reason => ({ status: 'indeterminate', reason })
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const count = value => Number.isSafeInteger(value) && value >= 0

export function validateEvidence(name, data, context = {}) {
  if (!record(data)) return unknown('Evidence is not an object')
  if (name === 'process-exit') {
    for (const flag of ['terminationConfirmed', 'timedOut', 'aborted', 'outputLimitExceeded']) {
      if (data[flag] !== undefined && typeof data[flag] !== 'boolean') return unknown('Process metadata is malformed')
    }
    if (data.terminationConfirmed === false) return unknown('Process termination was not confirmed')
    if (data.startError) return failed('Process could not be started')
    if (data.timedOut === true) return failed('Process exceeded its deadline')
    if (data.aborted === true) return failed('Process was cancelled')
    if (data.outputLimitExceeded === true) return failed('Process exceeded the output limit')
    if (data.signal !== null && data.signal !== undefined) return failed('Process ended by signal')
    if (!Number.isInteger(data.exitCode)) return unknown('Process exit code is missing')
    return data.exitCode === 0 ? passed() : failed('Process returned a nonzero exit code')
  }
  if (name === 'assertions') {
    if (data.complete !== true) return unknown('Assertion evidence is incomplete')
    if (!Array.isArray(data.assertions) || data.assertions.length === 0) return failed('No assertions were reported')
    const seen = new Set()
    for (const assertion of data.assertions) {
      if (!record(assertion) || typeof assertion.id !== 'string' || !assertion.id.trim() ||
          typeof assertion.passed !== 'boolean' || seen.has(assertion.id)) {
        return unknown('Assertion evidence is malformed or duplicated')
      }
      seen.add(assertion.id)
    }
    if (context.expectedAssertions !== undefined) {
      if (!Array.isArray(context.expectedAssertions) || context.expectedAssertions.some(id => typeof id !== 'string' || !id)) {
        return unknown('Expected assertion contract is malformed')
      }
      if (context.expectedAssertions.some(id => !seen.has(id))) return failed('A required assertion was not reported')
    }
    return data.assertions.every(assertion => assertion.passed) ? passed() : failed('An assertion failed')
  }
  if (name === 'test-summary') {
    if (data.complete !== true) return unknown('Test evidence is incomplete')
    // The caller must supply the run/source identities; an unbound report is not proof.
    if (typeof context.runId !== 'string' || !context.runId ||
        typeof context.sourceDigest !== 'string' || !context.sourceDigest ||
        data.runId !== context.runId || data.sourceDigest !== context.sourceDigest) {
      return unknown('Test evidence does not match this run and source')
    }
    if (!['tests', 'failures', 'errors', 'skipped'].every(key => count(data[key]))) {
      return unknown('Test counts are missing or invalid')
    }
    if (data.failures + data.errors + data.skipped > data.tests) return unknown('Test counts are inconsistent')
    if (data.tests === 0 || data.tests === data.skipped) return failed('No tests were executed')
    return data.failures === 0 && data.errors === 0 ? passed() : failed('Tests reported errors or failures')
  }
  return unknown('Evidence validator is not supported')
}
