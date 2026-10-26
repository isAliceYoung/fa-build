# WebDesktop Public Bootstrap

This public repository contains only a small, auditable Debian 12 amd64 bootstrap. WebDesktop application code, runtime packages, databases and user data remain outside this repository, in the separately authorized private project.

The published startup command must name a reviewed **full fa-build commit** and compare the fetched SHA before executing bootstrap.sh. Obtain that commit through an independent administrator channel. Do not execute an arbitrary latest main, a downloaded unverified script, or curl piped to a shell. The maintainer's handoff report supplies the exact one-line command for each release; the repository cannot authenticate its own latest version.

## Interactive flow

Run only as root on a separately authorized Debian 12 amd64 host with systemd/cgroup v2. Basic Git/Python/OpenSSH/CA tools are prepared when absent. On first key creation the script prints its actual checkout path, a per-host public Deploy Key, and https://github.com/isAliceYoung/fa/settings/keys. Add the public key in Deploy keys with **Allow write access disabled**. At `是否已完成 GitHub 授权？[y/N]:`, only y/Y proceeds. Empty input, n/N, EOF and invalid input exit safely.

Confirmation is not authentication: pinned GitHub SSH host verification, real repository read access, approved feature/CC ancestry and exact commit checks follow. Existing matching keys and clean exact checkouts are reused. Unknown or modified state is preserved and refused. The private deployment entrypoint and source helper also have pinned file hashes in release.json.

An existing identity must pass strict local ownership, permissions, keypair and pinned-host/configuration checks, followed by live read authorization. A valid authorized key is reused without printing the key or asking y again. An invalid, incomplete or revoked identity stops without replacement or repair. Review the existing key and GitHub authorization manually; do not delete key files to bypass the refusal.

The generic scripts/private_repo.py authorization helper is intentionally shared with the private project and reviewed for public distribution. It contains no application code, credentials or Git history. The public repository is created independently, never by publishing the application's Git directory.

## Trust modes

- **formal** is the default. It requires an administrator-preprovisioned, independently signed delivery package, its independently confirmed SHA256, and an independently registered release signer. Pass `--formal-package` and `--formal-package-sha256` when these materials exist. Missing materials stop the process; no local signer is substituted. Prebuilt artifacts are used rather than pretending to have independently signed a local build.
- **local-test** requires `--mode local-test --ack-local-test-trust`. The host builds as wdbuild, creates a separate local signing identity, and explicitly labels the installation **LOCAL_TEST_TRUST**. The key is not the GitHub Deploy Key. A separate local-test-cc channel and reserved signer names prevent implicit promotion to independent release trust. This mode is for explicitly authorized tests, not production acceptance.

Both modes additionally require `--authorize-install --authorize-isolated-egress` in the initial command. These authorize deployment on the host where the operator executes that command; they do not authorize anyone to remotely operate an existing server. After those explicit flags and GitHub key registration, the only interactive input is y. Formal mode can proceed with just y only if its independent trust materials have already been prepared.

## Preparation, resources and boundaries

Local builds target 2 vCPU, 2 GiB RAM, 2 GiB effective Swap and approximately 15 GiB initial free disk on a 20 GiB disk. CPU/memory/cgroup/disk checks are enforced, not inferred from nominal VPS sizes. Correct existing Node22.23.2/ABI127 and Swap are reused. A mismatched existing Node installation is preserved and requires review. An absent Node toolchain is downloaded only from the fixed official Node distribution URL and checked against the pinned independent SHA256 in platform_tools.py before extraction. The source is [Node's official release checksum file](https://nodejs.org/dist/v22.23.2/SHASUMS256.txt); changing the pin requires a new reviewed public commit.

No npm build runs as root or a service/guest account. Git credentials stay in a root-only state directory and are not passed to wdbuild. Builds have memory/process/log/tree/disk limits. Each later stage rechecks disk; same-filesystem moves reduce peak duplication. Only journal-owned, verified, obsolete scratch is cleaned. Source, keys, signing audit, database, files, Profile, credentials and installed releases are retained.

Prepared private sources live under `/opt/webdesktop-private-build/sources/<approved-sha>`; formal sources under `/opt/webdesktop/source` are created only by the verified installation engine. Old SHA copies are preserved, never reset into the new version. Existing deployments, databases or interrupted installs block fresh installation. No domain, Cloudflare, SSH public keys, proxy or public management port is changed automatically. The browser's isolated namespace/nft/forwarding setup needs the explicit egress flag.

## Status and re-entry

The terminal prints the public checkout path at startup. For an already verified checkout at `/root/fa-build.REVIEWED`, read-only status is one line:

```bash
bash /root/fa-build.REVIEWED/bootstrap.sh status
```

`fa-build.REVIEWED` is a clearly marked path placeholder: substitute the actual verified directory printed by your startup command. Retry pre-install preparation from that same checkout using the original mode and authorization flags; `resume` re-enters only the safe preparation flow:

```bash
bash /root/fa-build.REVIEWED/bootstrap.sh resume --mode local-test --ack-local-test-trust --authorize-install --authorize-isolated-egress
```

Every re-entry rechecks Git authorization and the approved source. Authentication/dependency failures can be retried without replacing valid keys or versions. Partial builds/signatures or an installing journal stop for root review. This is not automatic recovery of every installation phase. Preserve `/var/lib/webdesktop-bootstrap`, `/var/lib/webdesktop-fresh`, source/artifacts and native diagnostics. Do not delete state, reset databases or clear profiles to bypass a refusal.

Failures report a reviewed stage/code/category, a known tool name, exit code when available and `/var/log/webdesktop-deploy/events.jsonl`. That directory is root 0700 and the metadata-only log is root 0600 with no ACLs or links. No raw subprocess output, arguments, environment or exception message is written to it. Before Python is available, failed basic-tool preparation uses `/var/log/webdesktop-bootstrap-tools/events.jsonl`, also root-only. Raw APT output is suppressed. If safe diagnostics cannot be established the process stops. Read-only status does not start installation or reset journals.

Failure records also include the reviewed source module, line number and a static human-readable cause. `Where:` and `Reason:` preserve the original location through verified installation launchers. Absolute paths, traceback source/locals and arbitrary exception text are withheld. Unknown causes remain explicitly unclassified; the source line is supplied when available. Existing version-1 error records remain readable. Output from unrelated external tools cannot claim an installer source location through a forged error marker.

Non-project host accounts remain administrator-managed and are not audited or modified by the installer. Interactive shells, valid passwords, SSH authorization and extra groups of ordinary vendor accounts do not alone block installation. Fresh and native preflight share root authorization, strict wdbuild validation and reserved project user/group conflict checks. Host inventory names confer no WebDesktop administrator role. No strict/compatibility mode is offered. New journals do not record host-account-policy evidence. Historical journals with that input are preserved and refuse automatic replay; an early interrupted installation without a native journal is not replayed, including when its signed source still exists.

After successful installation, use the original read-only status interface and read credentials locally as root:

```bash
bash /opt/webdesktop/source/webdesktop-deploy/install-fresh.sh status
```

Credentials are in `/etc/webdesktop-isolated/login.json`; ordinary output only gives this path. Native diagnostics are under `/etc/webdesktop-isolated/install.log`. The service listens at `http://127.0.0.1:3000`; a public HTTPS access path requires separately authorized administration.

Application updates retain the private project's existing root executor and administrator reauthentication. The public bootstrap does not implement git pull updates or bypass system-layer compatibility. Automatic in-place system-layer upgrades remain unavailable.

## Evidence limits

Fast tests use local simulations, local Git and throwaway keys only. They do not prove real private GitHub permissions, Debian builds, Linux DAC/systemd behavior, first installation, PostgreSQL, Chromium, GUI or VPS reliability. Those remain **NOT RUN** until a separately authorized test occurs. No Actions or VM workflow is shipped here.

Review public contents and all committed trees using `python3 tests/audit_public.py`. Run interaction simulations with `python3 tests/test_bootstrap.py`. No private application tree or history should ever be imported here.
