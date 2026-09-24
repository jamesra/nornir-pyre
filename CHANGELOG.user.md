# Pyre user changelog

Curated notes for **end users** of the Windows installer (not a full developer git log).
Maintainers: add a new ``## X.Y.Z`` section at the **top** when cutting a Pyre release.
CI copies that section into the GitHub Release body and regenerates
``docs/packages/pyre_changelog.rst``.

## 1.7.7

- Cancel in-flight control-point registrations (including refine-grid work) when you open a different ``.stos`` file, so the UI does not keep applying edits from the previous pair.
- Faster feedback when Spacebar registration points fall on blue/busy or masked regions: both source and target masks are checked before a registration job is queued.
- Installer and documentation packaging updates for the Windows build.

## 1.7.6

- Baseline Windows installer release used with the Nornir monorepo ``v1.7.6`` line.
