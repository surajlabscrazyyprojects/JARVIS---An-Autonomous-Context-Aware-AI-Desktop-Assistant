# Public release preparation

## Security changes

- Excluded environment files, runtime memory, browser state, caches, logs, backups, and local diagnostic artifacts from publication.
- Removed a credential-looking value from `CHARACTER_SYSTEM.md`; provider credentials remain environment-only.
- Documented backend-only Hume/Groq/Fish credential handling.

## Documentation changes

- Updated README configuration and licensing notes to match the current architecture.
- Added concise contributor guidance and refreshed the security policy.

## GitHub metadata changes

- The repository was initialized locally on `main`; no GitHub remote or publication was performed because GitHub authentication was unavailable.

## Workspace cleanup

- Quarantined confirmed one-off repair scripts, test captures, logs, and superseded HUD snapshots under the ignored `_PROJECT_QUARANTINE/` folder.
- Removed generated website workspaces from the Git release index while preserving them locally.
- Kept the existing application root and startup paths unchanged to avoid runtime regressions.
