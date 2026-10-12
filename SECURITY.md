# Security policy

Character Studio is a single-user, local-first application. It binds only to `127.0.0.1`, keeps private photos and its database outside the source folder, and never reads or stores the logins of the AI command-line tools. Optional API keys that the user enters are encrypted with Windows DPAPI for the current Windows user, never shown again, never included in backups and sent only to their own provider. Backups can be encrypted with a password (AES-256-GCM, key derived with scrypt); the password is never stored. See the [User Guide](docs/USER_GUIDE.md#storage-and-configuration) for the full local security model.

## Supported versions

Only the latest commit on `main` receives fixes.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub's **[Report a vulnerability](https://github.com/CyberSecurityChuck/Character-Studio/security/advisories/new)** form (Security tab → Advisories). Please include:

- what you found and where (file, endpoint or workflow);
- steps to reproduce, using synthetic data only;
- the impact you expect (for example data exposure, path traversal or cross-origin access).

**Never include real personal photos, credentials, tokens or private data in a report.**

You can expect an acknowledgement within a few days. This is a personal project maintained in spare time, so fixes are made on a best-effort basis.

## In scope

- Exposure of the local service beyond the loopback interface
- Bypassing the host/origin checks or the per-process request token
- Path traversal, unsafe file handling or upload validation flaws
- Private data (photos, database, logs) leaking into the repository, exports or logs
- Any path where the app could read, store or forward the login credentials of the `claude` or `codex` command-line tools
- Leaking an API key (to logs, job folders, error messages, backups, the browser or any host other than its own provider)
- Weaknesses in password-protected backups (`backend/backup_crypto.py`), or a way to make the app follow a provider-supplied link to an untrusted host
- Paid API runs that start without the user's confirmation, or that are retried automatically

## Out of scope

- Attacks that require existing local administrator access or physical access to the computer
- Issues in third-party services (Anthropic, OpenAI, Google, Black Forest Labs) or in the official CLIs themselves; report those to the vendor
- A forgotten backup password (by design it cannot be recovered)
- The quality or likeness of AI-generated images
