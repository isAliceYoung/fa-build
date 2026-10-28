# WebDesktop Public Bootstrap

## Optional automatic HTTPS domain binding

After WebDesktop **1.8.0** and the Claude Desktop package are installed successfully, the root terminal asks `是否绑定域名？[y/N]：`. Choose y to enter Cloudflare Account ID, Zone ID for `ourgoal.win`, and the account API Token using hidden terminal input. The machine ID is read automatically. The private provisioner creates a separate Tunnel and random 24-hex subdomain for this VPS, binds it to `http://127.0.0.1:3000`, and verifies connector readiness, HTTPS health and unauthenticated API refusal before reporting success. Choosing n/Enter/EOF skips binding.

The administrator explicitly authorizes temporary API Token use on the VPS. The token stays in process memory: no argv, environment, file or diagnostic-log token interface; no subprocess receives it. Core dumps are disabled and token references are dropped before package/service setup. Persistent root-only files contain only the dedicated per-VPS Tunnel credential, binding/provisioning state and IDs. The running connector never receives the account API Token. Do not put the token into a command, chat or repository.

Use an API Token scoped to **Cloudflare Tunnel: Edit** for the intended account and **DNS: Edit** only for `ourgoal.win`. The same account and existing zone reuse their Account ID and Zone ID across new VPS deployments; recheck after changing accounts or recreating/moving a zone. See [Cloudflare's ID guide](https://developers.cloudflare.com/fundamentals/account/find-account-and-zone-ids/).

Automatic binding supports the fixed 1.8.0, 1.7.0, 1.6.0 and 1.5.0 application commits. Older versions and Beta are unchanged and skip this feature. `domain-maintenance.json` separately pins the private maintenance commit and all six helper hashes; the installer uses the existing isolated Deploy Key and verified GitHub host to obtain that exact code. The 1.8.0 entry is the default; all previously published tags and version mappings remain unchanged. This avoids substituting maintenance code for the signed installed application.

After skipping or a reviewed recoverable binding failure, run the dedicated action from this **updated, reviewed** checkout:

```bash
bash /root/fa-build/install.sh domain
```

It requires an already complete protected installation; it does not replay fresh installation, npm builds or Claude installation. Existing matching binding data is verified and reused without another API Token. Unknown/partial application state, conflicting configuration or an uncertain Tunnel-create request stops for administrator review; no database, password, user data or DNS belonging to others is deleted. Binding can briefly restart the desktop backend, so save pending work before choosing y.

The earlier Windows administrator workflow and `--domain-config /root/webdesktop-domain.json` remain supported; that mode keeps the account API Token on Windows and passes only the per-Tunnel handoff. An already supplied domain handoff does not trigger another binding prompt. New integrated Cloudflare provisioning, Debian service and GUI acceptance remain **NOT RUN**; local tests use simulated services/API calls.

The isolated installation entrypoint now also installs the official Claude Desktop Linux package and GNOME Keyring after WebDesktop passes its health check. Anthropic's APT signing key must match `31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE`; unknown existing APT configuration is not overwritten. This does not change Beta installation or any published version-to-commit mapping.

**Package installation is not Claude GUI acceptance.** From WebDesktop 1.4.0, registered GUI apps share the existing filtered public HTTP/HTTPS namespace; host/private/metadata access remains blocked. Earlier versions retain their fixed system-layer behavior. Releases declaring `CLAUDE_DESKTOP_SUPPORT=1` also register the official launcher after package installation, using their verified Private coordinator. Those releases provide the desktop/Start menu icon, a non-root Electron browser worker, private Secret Service and persistent profiles. They require this supporting bootstrap; an older bootstrap stops before application installation instead of silently skipping registration. Older fixed releases, including 1.6.0, keep their original package-only behavior; this bootstrap does not retrofit their system layers. Electron's sandbox remains enabled and KVM access is not granted. New Claude startup/login/keyring/resource behavior still needs Debian acceptance; local tests are not a real VPS result. Component errors preserve the working desktop, its credentials and protected diagnostics; do not rerun the full fresh installer over an installed desktop. The standalone `python3 -I /root/fa-build/scripts/claude_desktop.py` prepares the package only, and does not register or upgrade a launcher.

This public repository contains only a small, auditable Debian 12 amd64 bootstrap. WebDesktop application code, runtime packages, databases and user data remain outside this repository, in the separately authorized private project.

Two startup choices are available: the convenience command trusts this official repository's current HTTPS `main`; the reproducible command checks out an independently reviewed **full fa-build commit before executing any repository script**. This repository cannot independently authenticate its own source after it has started running. Both choices keep private application versions pinned to reviewed commits and file digests.

## Short startup and version selection

`install.sh` contains the clean environment and explicit local-test installation flags; `bootstrap.sh` contains platform checks, basic dependency preparation and safe diagnostics. It remains root-only, Debian 12 amd64, for a new installation. The convenience command does not require manually editing a public commit:

```bash
(command -v git >/dev/null 2>&1 && test -s /etc/ssl/certs/ca-certificates.crt || (apt-get update && apt-get install -y git ca-certificates)) && (test ! -L /root/fa-build && test -d /root/fa-build/.git || git clone -c core.hooksPath=/dev/null -c core.fsmonitor=false https://github.com/isAliceYoung/fa-build.git /root/fa-build) && bash /root/fa-build/install.sh
```

On a first run this clones current official public `main`, not an independently pinned bootstrap. On later runs it reuses the existing checkout without pulling, resetting, deleting, or cloning over it. Git/CA preparation is skipped when the tools already exist. The current bootstrap validates root ownership, safe path types/modes, official origin, tracked-file identity and a clean checkout; unknown/modified directories stop for review. Existing older checkouts are not automatically upgraded by this command. To use an independently reviewed bootstrap, use the pinned template below.

### Reconnect while waiting for GitHub authorization

If the clone completed and the SSH connection ended at the y/N prompt, do not clone again. From the existing reviewed checkout run:

```bash
bash /root/fa-build/install.sh
```

The current bootstrap reuses a locally validated key. Live authorization success skips the prompt; access denial shows the same public key and allows manual authorization again, then rechecks real read access. Broken/mismatched keys, host-key failures and network/branch errors stop without replacement or repair. y is not proof of authorization. Older bootstrap versions may require adding the existing key in GitHub before re-entry; its public half is `/root/.ssh/webdesktop-build-fa/deploy_key.pub`. Never delete or regenerate the key merely to get another prompt.

Completed root-protected native/bootstrap/fresh installation records are recognized and the command exits with `ALREADY_INSTALLED`, without reinstalling, upgrading, changing credentials or claiming a new health-check pass. Partial/failed records still refuse automatic replay. Preparation stages retain their original bounded reuse policy; an interrupted build or native installation is not blindly restarted. Check `bootstrap.sh status` before any separately reviewed recovery.

This is a **template**. Replace `APPROVED_PUBLIC_SHA` with the independently approved full public commit. `/root/fa-build` must not exist; the command never overwrites an existing directory.

```bash
apt-get update && apt-get install -y git ca-certificates && git clone -n -c core.hooksPath=/dev/null -c core.fsmonitor=false https://github.com/isAliceYoung/fa-build.git /root/fa-build && git -C /root/fa-build checkout --detach APPROVED_PUBLIC_SHA && test "$(git -C /root/fa-build rev-parse HEAD)" = APPROVED_PUBLIC_SHA && bash /root/fa-build/install.sh
```

After GitHub read authorization, the bootstrap fetches the latest official version catalogue from `https://raw.githubusercontent.com/isAliceYoung/fa-build/main/release.json` over verified HTTPS. It then scans private repository tags through the existing pinned SSH identity, checks each listed version against its full approved commit (including annotated tags), prints the available versions in numeric descending order (stable before Beta), and prompts `请输入你要安装的版本：`. New registered releases do not require pulling this bootstrap checkout just to refresh the list. The following table is the catalogue snapshot shipped with this commit; the terminal can show newer reviewed entries:

| Input | Fixed commit | Installer |
| --- | --- | --- |
| `1.8.0` | `c1fe5497577049b9fa1b69fa9de7094f62cadd67` (`v1.8.0`) | Package names/icons, longer GUI cold-start waits, shared interactive resources and verified resource-policy continuation after a confirmed 1.7.0 update. |
| `1.7.0` | `f0c5ab044775a7060b563c0e055e484f165b2eb4` (`v1.7.0`) | Claude desktop launcher, Shift input switching, concurrent Claude/browser, adaptive Swap and controlled system-component updates preserving user data. |
| `1.6.0` | `9f1bc9329aba6e89b1301a74fcd0d99cf00ef3d0` (`v1.6.0`) | Post-Claude optional automatic Cloudflare subdomain and Tunnel provisioning, hidden temporary root API Token input, verified HTTPS binding. |
| `1.5.0` | `1fce41f13dd3b556384e58e35ff8efb1e08b0582` (`v1.5.0`) | Administrator HTTPS domain handoff, CC terminal compatibility and shared Claude configuration for CMCP 4.4.0. Changes system layers; old installations require reviewed root maintenance/migration. |
| `1.4.0` | `a31c680f4e85111a161466941a838409fff9036e` (`v1.4.0`) | Filtered GUI web access and Ctrl+C/X/V clipboard; removes GUI toolbars. Changes system-layer contracts; existing installations need root maintenance. |
| `1.3.0` | `ead5e46cba31d50e0be53738c4d855581c1c674e` (`v1.3.0`) | Desktop/settings refresh with Lucide, persistent image wallpapers and VPS clock; existing source updater/data preservation |
| `1.2.0` | `cb280d280d35212b23bd823e8f64727f6811d9c6` (`v1.2.0`) | CC isolated installation with pinned source updates, progress and verified user-data protection |
| `1.1.0` | `07f9adf18e133534e02ce9d9500af45dc8afb90b` (`v1.1.0`) | CC isolated installation with settings updates and simplified login UI |
| `1.0.0` | `73e544e32b67bee2ac17cca7f21b7cf5692d0482` (`v1.0.0`) | Existing CC isolated build/sign/verify/fresh installation |
| `beta0.1.0` | `5922e1408de91e56771f1ea0bf94a9df1b7028cd` (`v0.1.0-beta.1`) | Unchanged Beta installer with offline source handoff |

Invalid input prints `该版本不可用` and asks again; empty input/EOF exits without installation. Omit `--version` to select interactively. `--version 1.0.0` deliberately selects that exact version without prompting. Missing private tags are not offered; moved tags, malformed listings and authorization failures stop installation. Publishers still add audited fixed metadata to the official catalogue when releasing a version; an unregistered private Release or tag alone is not installable. The VPS refreshes that online catalogue automatically rather than relying on its old bundled list. This is an official catalogue plus live private-tag check, not a private GitHub Releases API request. No PAT is needed.

Catalogue downloads have a fixed HTTPS URL, normal certificate verification, no redirects/proxy inheritance, a 20-second request timeout, a 64-KiB body bound and a closed schema/128-version bound. Known version entries cannot be rewritten relative to this reviewed checkout; publisher withdrawals are respected. Download/validation failure stops before version selection or source acquisition, without silently falling back to stale bundled metadata. The catalogue only supplies metadata, never downloaded executable bootstrap code. Changing the source-authorization helper contract requires a reviewed bootstrap upgrade. Domain-maintenance helper support remains independently pinned by the local `domain-maintenance.json`; future versions requiring different binding/installer capabilities can require an updated bootstrap.

The version catalogue is an explicitly online trust authority controlled by the publisher, including when bootstrap code is pinned. The pinned command fixes the bootstrap implementation; it does not freeze all future offered versions. Private tag/commit, entrypoint/hash and release signature checks still apply. Formal mode continues to require independently prepared signed materials; LOCAL_TEST_TRUST does not become independent release trust.

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

Both modes require `--authorize-install --authorize-isolated-egress` (`install.sh` supplies these for its explicit local-test workflow). These authorize installation on the host where the operator executes the command, not remote operation of an existing server. The interactive inputs are first-key authorization y/Y when needed, then a version; 1.7.0, 1.6.0 and 1.5.0 also offer optional post-Claude domain binding and its Cloudflare inputs. Formal mode also requires independently prepared materials and supports only the isolated engine.

## Preparation, resources and boundaries

Local builds target at least 2 vCPU and approximately 2 GiB effective RAM. New private coordinator code selects Swap using Beta's RAM tiers: below 2 GiB prefers 4 GiB Swap, 2–8 GiB prefers 2 GiB, and at least 8 GiB adds none. Smaller candidates must fit the existing disk reserve (10 GiB for local builds) and minimum usable Swap (approximately 2 GiB for local builds below 8 GiB RAM). Existing managed Swap is preserved; insufficient or inactive existing objects require review instead of replacement. The selected target is recorded and reused by both installation preflights. Published version mappings remain unchanged; older versions retain their own preparation policy. CPU/memory/cgroup/disk checks are enforced, not inferred from nominal VPS sizes. Correct existing Node22.23.2/ABI127 and Swap are reused. A mismatched existing Node installation is preserved and requires review. An absent Node toolchain is downloaded only from the fixed official Node distribution URL and checked against the pinned independent SHA256 in platform_tools.py before extraction. The source is [Node's official release checksum file](https://nodejs.org/dist/v22.23.2/SHASUMS256.txt); changing the pin requires a new reviewed public commit.

For the isolated engine, no npm build runs as root or a service/guest account. Git credentials stay in a root-only state directory and are not passed to wdbuild. Builds have memory/process/log/tree/disk limits. Each later stage rechecks disk; same-filesystem moves reduce peak duplication. Only journal-owned, verified, obsolete scratch is cleaned. Source, keys, signing audit, database, files, Profile, credentials and installed releases are retained. Beta retains its original unprivileged application account for npm, not the CC wdbuild sandbox.

Prepared private sources live under `/opt/webdesktop-private-build/sources/<approved-sha>`; isolated deployment sources under `/opt/webdesktop/source` are created only by the verified installation engine. Old SHA copies are preserved. Existing deployments, databases or interrupted installs block fresh installation. SSH public keys, proxies and the administrator inbound firewall are preserved. From 1.5.0 the backend listens only on 127.0.0.1:3000; without a domain handoff use an administrator SSH tunnel or a separately reviewed HTTPS proxy. Supplying an approved domain handoff installs that one dedicated Tunnel without requesting an account token. Alternatively, after successful 1.7.0, 1.6.0 or 1.5.0/Claude installation, the optional root-terminal flow temporarily reads the account API Token to create and bind a new per-VPS Tunnel. Earlier fixed versions retain their previous listener behavior. Existing IPv6 kernel controls are disabled and persisted; absent support is skipped. An active IPv6 SSH session is refused rather than cut off. Beta retains its original network setup.

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

Credentials are in `/etc/webdesktop-isolated/login.json`; ordinary logs only give this path. Native diagnostics are under `/etc/webdesktop-isolated/install.log`. For 1.7.0, 1.6.0 and 1.5.0, use the verified HTTPS URL after domain binding. If binding is skipped, the backend remains server-local at `127.0.0.1:3000`; administrator SSH forwarding or a separately reviewed HTTPS proxy is required. Older fixed versions retain their original listener behavior. Desktop/admin authentication and same-origin checks remain. Existing installations are not automatically rebound or repaired.

After the isolated coordinator returns from successful installation and health checks, this public wrapper automatically executes `/usr/bin/cat -- /etc/webdesktop-isolated/login.json`. It validates the protected root-owned path first and sends the initial credentials directly to the operator's controlling terminal (`/dev/tty`), not captured stdout, stderr, diagnostic records or installation logs. If no controlling terminal is available, or the safe read fails, installation remains successful and the manual read command is printed instead. External terminal/session recording can still record what the operator sees. The file contains initial credentials; later changed passwords remain in the database and are not replaced by the old seed during updates. Failed installation or health checks never execute the credential display. No existing version tag or private application code is changed by this wrapper improvement.

From 1.1.0, signed application updates in desktop Settings require an active desktop session and explicit confirmation, without retyping an administrator or desktop password. Root still independently verifies the session and one-use confirmation, the signed prepared release and system-layer compatibility. History cleanup retains administrator reauthentication. The public bootstrap does not implement git pull updates. Automatic in-place system-layer upgrades remain unavailable. GitHub source assets are not signed online-update runtime packages.

From 1.2.0, new signed isolated installations enable the web update service by default. LOCAL_TEST_TRUST installations can discover newer stable versions from this fixed catalogue, verify the private SSH tag/commit, build under the existing wdbuild sandbox, then sign and verify locally before the original transactional updater switches versions. Existing registered keys are reused, not replaced. Guest HOME (downloads, Chromium Profile and GUI configuration), runtime credentials and PostgreSQL have protected backups and retention checks. Prepared-source stages and elapsed time are persisted; switching briefly stops the backend, and progress resumes after reconnection. Formal mode still requires independent signed runtime preparation. Existing 1.1.0 does not contain this source updater: first adoption needs a separately verified root maintenance checkout, not a fresh install over existing data. Real Debian upgrades and GUI/data retention remain NOT RUN.

For Beta, the original check command is `bash /usr/local/lib/webdesktop-deploy/check.sh`. Initial credential seeds are in `/home/webdesktop/webdesktop/.env`; read locally as root/the application user, never publish. Beta keeps its original `http://127.0.0.1:3000` binding and network behavior. `bash /root/fa-build/install.sh status` reads preparation journals, including Beta. Interrupted installation requires manual review; no reset or automatic replay is provided.

## Evidence limits

The automatic online-catalogue follow-up passed **98 local Public tests**, including 17 new cases for newly offered versions without a local catalogue update, exact HTTPS/timeout/size controls, malformed/duplicate metadata, null-root rejection, changed pins/helper contracts, withdrawals, numeric sorting, consent/request order and invalid input retries. A cross-module flow test also authorizes, refreshes a newly listed version, checks live tag pins, rejects an unavailable input, and delegates only the selected fixed/hash-verified source once. Network transports and service effects are simulated in these tests. Real Debian/VPS installation remains NOT RUN. This follow-up changes only the public bootstrap, not the Private v1.6.0 release or old version mappings.

The post-Claude interactive domain addition passed **81 Public local tests** and **226 Private targeted tests (223 passed, three skipped)**. The dedicated suites cover 17 root provisioning cases and 15 public routing/catalogue/order cases; the 1.6.0 admission test and the 12 hardlink/23 .next-mode regressions also passed. Public working files and all historical committed trees passed the explicit allowlist, size, helper provenance and secret-pattern audit. These are Windows-hosted simulations, not Debian or live Cloudflare results.

The 1.6.0 catalogue retains all previous version-to-commit mappings and pins the new private entrypoint/helper digests. The new release adds installation orchestration without changing the 1.5.0 GUI/PTY system-layer contracts. Local routing/authorization/credential-display/component tests and the public-tree/history audit do not install a VPS. Versions before 1.5.0 have different GUI/PTY system layers and require separately reviewed root maintenance and Claude configuration migration. The web updater must retain its compatibility refusal. Use the fresh command only on a new server without deployment state. LOCAL_TEST_TRUST is not independent production signing.

The automatic credential-display/live-tag follow-up passed 45 local bootstrap/version tests, Python syntax checks and shell syntax checks. Public working files and all historical trees were audited. Tests simulate SSH tags, installation/health outcomes and the Linux controlling terminal/cat process; actual Linux terminal display is NOT RUN. No actual VPS was contacted or modified. The existing private updater's data/authentication subset ran 43 local cases (42 passed, one Linux-only case skipped), which is not evidence of a real Debian upgrade preserving passwords.

Fast tests use local simulations, local Git and throwaway keys only. They do not prove real private GitHub permissions, Debian builds, Linux DAC/systemd behavior, first installation, PostgreSQL, Chromium, GUI or VPS reliability. Those remain **NOT RUN** until a separately authorized test occurs. No Actions or VM workflow is shipped here.

Review public contents and all committed trees using `python3 tests/audit_public.py`. Run interaction simulations with `python3 tests/test_bootstrap.py`. No private application tree or history should ever be imported here.

Run version checks with `python3 -m unittest discover -s tests -p 'test_*.py' -v`. The offline Git handoff uses a real local bundle/clone; Linux account ownership and modes are modeled. Original Beta installation, APT, systemd, PostgreSQL, GUI and real VPS deployment are **NOT RUN**. No private application source or runtime archive is included in this public repository.

## 1.7.0 update boundary

Version 1.7.0 includes the new controlled system-component migration engine. A desktop already running 1.6.0 still uses its old updater and cannot bootstrap this system-layer change through the Settings button. An administrator must introduce the published fixed 1.7.0 engine once through its protected source-update entrypoint; do not run fresh installation over an existing deployment. Downloads, browser and Claude profiles, keyrings, desktop/admin passwords, database and domain identity are retained and verified. Unknown changes or unverifiable state stop for review. Successful real Debian 1.6.0-to-1.7.0 adoption has NOT RUN.

New installations should use this updated bootstrap for 1.7.0 domain binding: old local domain-maintenance metadata still supports only its pinned versions. Updating the online version list alone does not update those local capabilities. Existing tags and version mappings are unchanged. This release does not upgrade Debian, existing native packages, Node/PostgreSQL, Swap size or arbitrary system topology during a web update.

## 1.8.0 resource-policy continuation

For a supported signed 1.7.0 installation, the existing updater first commits the verified 1.8.0 application/system components. The new authenticated broker resumes a fixed resource-policy transaction under that original confirmed job; it does not ask for another password or Deploy Key. Progress stays pending until resource checks, backups, changes, readback and the matching recovery seal all pass. Unknown policies, modified files, insufficient effective capacity or unproven states stop for review. Existing explicit administrator budget reductions are retained. New installations start with revision 2 directly.

This is two linked transactions: a resource failure restores resource settings while the verified newer application remains installed. User files, browser/Claude profiles, passwords, database and domain identity are never restored over newer data. Interrupted live resource work rolls backwards only after proofs; unknown states hold maintenance for root review. A failed resource attempt is not automatically replayed forwards. Original 1.7.0 pages also receive a pending/failure projection, rather than a premature success. Real Debian 1.7.0-to-1.8.0 acceptance remains NOT RUN; Windows models are not VPS results.
