# WebDesktop Public Bootstrap

The isolated installation entrypoint now also installs the official Claude Desktop Linux package and GNOME Keyring after WebDesktop passes its health check. Anthropic's APT signing key must match `31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE`; unknown existing APT configuration is not overwritten. This does not change Beta installation or any published version-to-commit mapping.

**Package installation is not Claude GUI acceptance.** The current offline GUI worker cannot sign in to Claude; this installer does not weaken its sandbox, grant KVM access, or automatically register an unusable launcher. Debian package installation and login/keyring/resource tests remain NOT RUN locally. Component errors preserve the working desktop and `/var/lib/webdesktop-claude-bootstrap/status.json`; after root reviews the cause, retry only this component with `python3 -I /root/fa-build/scripts/claude_desktop.py`. Do not rerun the full fresh installer over an installed desktop.

This public repository contains only a small, auditable Debian 12 amd64 bootstrap. WebDesktop application code, runtime packages, databases and user data remain outside this repository, in the separately authorized private project.

Two startup choices are available: the convenience command trusts this official repository's current HTTPS `main`; the reproducible command checks out an independently reviewed **full fa-build commit before executing any repository script**. This repository cannot independently authenticate its own source after it has started running. Both choices keep private application versions pinned to reviewed commits and file digests.

## Short startup and version selection

`install.sh` contains the clean environment and explicit local-test installation flags; `bootstrap.sh` contains platform checks, basic dependency preparation and safe diagnostics. It remains root-only, Debian 12 amd64, for a new installation. The convenience command does not require manually editing a public commit:

```bash
apt-get update && apt-get install -y git ca-certificates && git clone -c core.hooksPath=/dev/null -c core.fsmonitor=false https://github.com/isAliceYoung/fa-build.git /root/fa-build && bash /root/fa-build/install.sh
```

This executes the current official public `main`, not an independently pinned bootstrap. `/root/fa-build` must not already exist; no old checkout, installed system or failed journal is overwritten. To choose an independently reviewed bootstrap instead, use the following pinned template.

This is a **template**. Replace `APPROVED_PUBLIC_SHA` with the independently approved full public commit. `/root/fa-build` must not exist; the command never overwrites an existing directory.

```bash
apt-get update && apt-get install -y git ca-certificates && git clone -n -c core.hooksPath=/dev/null -c core.fsmonitor=false https://github.com/isAliceYoung/fa-build.git /root/fa-build && git -C /root/fa-build checkout --detach APPROVED_PUBLIC_SHA && bash /root/fa-build/install.sh
```

After GitHub read authorization, the bootstrap scans private repository tags through the existing pinned SSH identity, checks each registered version against its full approved commit (including annotated tags), then prompts `请输入你要安装的版本：`:

| Input | Fixed commit | Installer |
| --- | --- | --- |
| `1.2.0` | `cb280d280d35212b23bd823e8f64727f6811d9c6` (`v1.2.0`) | CC isolated installation with pinned source updates, progress and verified user-data protection |
| `1.1.0` | `07f9adf18e133534e02ce9d9500af45dc8afb90b` (`v1.1.0`) | CC isolated installation with settings updates and simplified login UI |
| `1.0.0` | `73e544e32b67bee2ac17cca7f21b7cf5692d0482` (`v1.0.0`) | Existing CC isolated build/sign/verify/fresh installation |
| `beta0.1.0` | `5922e1408de91e56771f1ea0bf94a9df1b7028cd` (`v0.1.0-beta.1`) | Unchanged Beta installer with offline source handoff |

Invalid input asks again; empty input/EOF exits without installation. `--version 1.0.0` selects a reviewed version without that prompt. Missing private tags are not offered; moved tags, malformed listings and authorization failures stop installation. Future stable/Beta versions require an audited catalogue update and a new public commit; an existing version never silently follows a changing branch. This is a live tag scan intersected with the reviewed catalogue, not an anonymous private GitHub Release API query. Unknown tags are not automatically approved. No arbitrary URL, branch, SHA or shell input is accepted.

**A release number is not a trust mode.** The short `install.sh` entrypoint explicitly uses **LOCAL_TEST_TRUST**, not independent production signing. For the isolated engine, advanced administrators can still run `bootstrap.sh` in formal mode with separately prepared signed materials. Legacy Beta is refused in formal mode: its original installer does not implement the CC signature/isolation contract.

The Beta adapter reuses the existing pinned SSH source helper, then creates an offline Git bundle and a separate fresh runtime checkout. No Deploy Key, SSH configuration or GitHub credential is given to its runtime account. The original installer receives that existing checkout and exact `--commit`, avoiding an anonymous clone of private fa. The Beta source, tag, account/build model, local-only listener, optional Claude behavior and scripts remain unchanged. It does not gain the CC isolation model. Existing users, deployments and failed journals are preserved and refused. Beta's root-only journal is `/var/lib/webdesktop-beta-bootstrap/state.json`; failures retain its source bundle for review.

## Interactive flow

Run only as root on a separately authorized Debian 12 amd64 host with systemd/cgroup v2. Basic Git/Python/OpenSSH/CA tools are prepared when absent. On first key creation the script prints its actual checkout path, a per-host public Deploy Key, and https://github.com/isAliceYoung/fa/settings/keys. Add the public key in Deploy keys with **Allow write access disabled**. At `是否已完成 GitHub 授权？[y/N]:`, only y/Y proceeds. Empty input, n/N, EOF and invalid input exit safely.

Confirmation is not authentication: pinned GitHub SSH host verification, real repository read access, version-specific branch ancestry and exact commit checks follow. Stable versions use feature/CC; the original Beta uses main. Existing matching keys and clean exact checkouts are reused. Unknown or modified state is preserved and refused. Entrypoints and the source helper have pinned file hashes in release.json.

An existing identity must pass strict local ownership, permissions, keypair and pinned-host/configuration checks, followed by live read authorization. A valid authorized key is reused without printing the key or asking y again. An invalid, incomplete or revoked identity stops without replacement or repair. Review the existing key and GitHub authorization manually; do not delete key files to bypass the refusal.

The generic scripts/private_repo.py authorization helper is intentionally shared with the private project and reviewed for public distribution. It contains no application code, credentials or Git history. The public repository is created independently, never by publishing the application's Git directory.

## Trust modes

- **formal** is the default. It requires an administrator-preprovisioned, independently signed delivery package, its independently confirmed SHA256, and an independently registered release signer. Pass `--formal-package` and `--formal-package-sha256` when these materials exist. Missing materials stop the process; no local signer is substituted. Prebuilt artifacts are used rather than pretending to have independently signed a local build.
- **local-test** requires `--mode local-test --ack-local-test-trust`. The host builds as wdbuild, creates a separate local signing identity, and explicitly labels the installation **LOCAL_TEST_TRUST**. The key is not the GitHub Deploy Key. A separate local-test-cc channel and reserved signer names prevent implicit promotion to independent release trust. This mode is for explicitly authorized tests, not production acceptance.

Both modes require `--authorize-install --authorize-isolated-egress` (`install.sh` supplies these for its explicit local-test workflow). These authorize installation on the host where the operator executes the command, not remote operation of an existing server. The interactive inputs are first-key authorization y/Y when needed, then a version. Formal mode also requires independently prepared materials and supports only the isolated engine.

## Preparation, resources and boundaries

Local builds target 2 vCPU, 2 GiB RAM, 2 GiB effective Swap and approximately 15 GiB initial free disk on a 20 GiB disk. CPU/memory/cgroup/disk checks are enforced, not inferred from nominal VPS sizes. Correct existing Node22.23.2/ABI127 and Swap are reused. A mismatched existing Node installation is preserved and requires review. An absent Node toolchain is downloaded only from the fixed official Node distribution URL and checked against the pinned independent SHA256 in platform_tools.py before extraction. The source is [Node's official release checksum file](https://nodejs.org/dist/v22.23.2/SHASUMS256.txt); changing the pin requires a new reviewed public commit.

For the isolated engine, no npm build runs as root or a service/guest account. Git credentials stay in a root-only state directory and are not passed to wdbuild. Builds have memory/process/log/tree/disk limits. Each later stage rechecks disk; same-filesystem moves reduce peak duplication. Only journal-owned, verified, obsolete scratch is cleaned. Source, keys, signing audit, database, files, Profile, credentials and installed releases are retained. Beta retains its original unprivileged application account for npm, not the CC wdbuild sandbox.

Prepared private sources live under `/opt/webdesktop-private-build/sources/<approved-sha>`; isolated deployment sources under `/opt/webdesktop/source` are created only by the verified installation engine. Old SHA copies are preserved, never reset into the new version. Existing deployments, databases or interrupted installs block fresh installation. Domains, Cloudflare, SSH public keys, proxies and the administrator inbound firewall are preserved. The isolated fresh installer listens on IPv4 0.0.0.0:3000 for direct desktop access. Existing IPv6 kernel controls are disabled and persisted using the reviewed IPv4-only setup; absent IPv6 support is skipped. Installation refuses an active IPv6 SSH session rather than cutting it off. The browser namespace/nft/forwarding setup still needs the explicit egress flag. Beta retains its original listener and network setup.

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

After a successful isolated installation, use the original read-only status interface and read credentials locally as root:

```bash
bash /opt/webdesktop/source/webdesktop-deploy/install-fresh.sh status
```

Credentials are in `/etc/webdesktop-isolated/login.json`; ordinary logs only give this path. Native diagnostics are under `/etc/webdesktop-isolated/install.log`. After a fresh install, open `http://<VPS-IPv4>:3000` using the server IPv4. No SSH tunnel is required; existing provider security groups and host firewall rules must permit TCP 3000. Desktop/admin authentication and same-origin checks remain. HTTPS/domain setup is separate. Public HTTP is unencrypted and browser system-clipboard features may require HTTPS. Existing installations are not automatically rebound or repaired.

After the isolated coordinator returns from successful installation and health checks, this public wrapper automatically executes `/usr/bin/cat -- /etc/webdesktop-isolated/login.json`. It validates the protected root-owned path first and sends the initial credentials directly to the operator's controlling terminal (`/dev/tty`), not captured stdout, stderr, diagnostic records or installation logs. If no controlling terminal is available, or the safe read fails, installation remains successful and the manual read command is printed instead. External terminal/session recording can still record what the operator sees. The file contains initial credentials; later changed passwords remain in the database and are not replaced by the old seed during updates. Failed installation or health checks never execute the credential display. No existing version tag or private application code is changed by this wrapper improvement.

From 1.1.0, signed application updates in desktop Settings require an active desktop session and explicit confirmation, without retyping an administrator or desktop password. Root still independently verifies the session and one-use confirmation, the signed prepared release and system-layer compatibility. History cleanup retains administrator reauthentication. The public bootstrap does not implement git pull updates. Automatic in-place system-layer upgrades remain unavailable. GitHub source assets are not signed online-update runtime packages.

From 1.2.0, new signed isolated installations enable the web update service by default. LOCAL_TEST_TRUST installations can discover newer stable versions from this fixed catalogue, verify the private SSH tag/commit, build under the existing wdbuild sandbox, then sign and verify locally before the original transactional updater switches versions. Existing registered keys are reused, not replaced. Guest HOME (downloads, Chromium Profile and GUI configuration), runtime credentials and PostgreSQL have protected backups and retention checks. Prepared-source stages and elapsed time are persisted; switching briefly stops the backend, and progress resumes after reconnection. Formal mode still requires independent signed runtime preparation. Existing 1.1.0 does not contain this source updater: first adoption needs a separately verified root maintenance checkout, not a fresh install over existing data. Real Debian upgrades and GUI/data retention remain NOT RUN.

For Beta, the original check command is `bash /usr/local/lib/webdesktop-deploy/check.sh`. Initial credential seeds are in `/home/webdesktop/webdesktop/.env`; read locally as root/the application user, never publish. Beta keeps its original `http://127.0.0.1:3000` binding and network behavior. `bash /root/fa-build/install.sh status` reads preparation journals, including Beta. Interrupted installation requires manual review; no reset or automatic replay is provided.

## Evidence limits

The automatic credential-display/live-tag follow-up passed 45 local bootstrap/version tests, Python syntax checks and shell syntax checks. Public working files and all historical trees were audited. Tests simulate SSH tags, installation/health outcomes and the Linux controlling terminal/cat process; actual Linux terminal display is NOT RUN. No actual VPS was contacted or modified. The existing private updater's data/authentication subset ran 43 local cases (42 passed, one Linux-only case skipped), which is not evidence of a real Debian upgrade preserving passwords.

Fast tests use local simulations, local Git and throwaway keys only. They do not prove real private GitHub permissions, Debian builds, Linux DAC/systemd behavior, first installation, PostgreSQL, Chromium, GUI or VPS reliability. Those remain **NOT RUN** until a separately authorized test occurs. No Actions or VM workflow is shipped here.

Review public contents and all committed trees using `python3 tests/audit_public.py`. Run interaction simulations with `python3 tests/test_bootstrap.py`. No private application tree or history should ever be imported here.

Run version checks with `python3 -m unittest discover -s tests -p 'test_*.py' -v`. The offline Git handoff uses a real local bundle/clone; Linux account ownership and modes are modeled. Original Beta installation, APT, systemd, PostgreSQL, GUI and real VPS deployment are **NOT RUN**. No private application source or runtime archive is included in this public repository.
