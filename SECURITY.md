# Bootstrap trust and disclosure

Use a full public commit obtained independently. Validate the fetched SHA before root execution. release.json pins the approved private branch/commit and entrypoint digests; it is not a self-established release signing root.

GitHub SSH uses the pinned Ed25519 key from [GitHub's official fingerprints](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints), strict host checking and a dedicated identity. No agent forwarding, password prompt, PAT, write-permission test, automatic unknown-key acceptance or alternate unverified SSH host is used. Reading a repository does not prove a Deploy Key was configured read-only; the administrator must verify GitHub's setting.

Formal trust and LOCAL_TEST_TRUST are separate. A local signer is only generated following explicit test-mode acknowledgment. Its private key never enters runtime packages, public Git, GitHub or service accounts. The test signer cannot be relabelled as an independent release signer by this workflow.

Do not post passwords, private keys, tokens, cookies, database URLs, user files or browser profiles in this repository or issue reports. Public keys are non-secret; use private contact with the maintainer for sensitive findings. A complete application-history secret audit is separate from this minimal repository's allowlist and pattern scan. Making a formerly public repository private cannot recall earlier copies.

Unknown paths, mismatched versions, failed signatures and partial installations are retained for review, not overwritten or repaired by disabling checks. This tool is not authorized to operate any existing server merely because its code has been published.

The shared diagnostics module is intentionally public generic orchestration code. It accepts only enumerated error metadata; it never publishes raw stderr, arbitrary exception messages, command arguments or environments. The public file audit permits the historical 12-file trees and the current 13-file tree (one added diagnostics module), without importing private application code or Git history. Existing Deploy Key reuse is a live authorization check, never an assumption based on an old successful journal.
