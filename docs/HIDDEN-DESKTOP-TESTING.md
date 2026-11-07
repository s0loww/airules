# Hidden-desktop testing: integration evidence

Integration date: 2026-11-04.

## Source and scope

The user supplied `D:\AI_Projects\hodden_test`, a portable extraction dated
2026-11-02 from the Contabilidad test contour. Reviewed inputs:
`README.ru.md`, `VERIFICATION.ru.md`, `config.example.psd1`,
`manifest.sha256.json`, runner evidence gates and final PS7/PS5.1 smoke reports.

The reusable policy now lives in `overlays/1c/rules/testing-1c.md` and is routed
by its hidden-desktop trigger. The 1C tester role points to that section and
accepts jUnit/log evidence for this channel. The common testing-contour template
declares the optional project bindings without machine paths or identities.

This change integrates instructions, not the executable toolkit. Its scripts,
binary dependencies, local config, reports and disposable databases are not
copied into the rules distribution. Projects bind their reviewed runner
explicitly. The existing `tools/agent-1c` runner remains a separate implementation;
no equivalence with the portable toolkit is assumed.

## Source evidence

The final reports supplied by the user record one passed scenario, zero failed
or skipped, vrunner exit 0 and buildstatus `0` on both PowerShell 7 (23 seconds)
and Windows PowerShell 5.1 (24 seconds). Both record two clients with hidden
windows, a test client observed, zero client/user-desktop windows, zero process
poll errors and successful copy deletion. These are historical source results;
this integration did not run a database or reproduce the Vanessa scenario.

Source report paths relative to the supplied directory:

- `reports/smoke-final-20261102/result.json`
- `reports/smoke-ps51-final-20261102/result.json`

The reference toolchain was platform 8.3.27.1989, VA single 1.2.043.28,
OneScript 1.9.4 and vanessa-runner 2.6.1. These are verified source versions,
not global installation requirements or claims about current releases.

## Rollout

The changed rule and tester role are included in the installed DSH policy
artifact `0.12.0-dev8`, after candidate startup and apply/rollback/reapply
checks. Earlier immutable artifacts remain unchanged. Each project separately
supplies paths, users, consistent snapshots, features and a fresh local smoke
result. The executable toolkit itself still requires a project binding.

This work supplies the hidden-UI test contract for the later comparison of 1C
verification/deploy methods. It does not choose or replace a project's deploy
method, broaden the trust configuration or enable `onec.deploy`.
