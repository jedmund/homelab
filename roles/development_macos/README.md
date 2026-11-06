# macOS GitLab runner

The `development_macos` role manages the user-mode shell runner on `mac-mini`
(`ssh mac`), its Ruby toolchain, job environment, and log rotation. It runs as
`justin` so Xcode can access the existing login keychain.

## Ruby and Bundler

The role ensures mise is installed through Homebrew, then uses mise to install
Ruby `3.4.11` from a precompiled binary. A `creates` guard skips installation
when that exact runtime exists. It installs Bundler `2.6.7` into a runner-owned
gem directory. It does not change the user's global mise selection or install
Fastlane globally; application jobs run `bundle install` using their committed
Gemfile.lock. Runtime upgrades require changing the pinned role default. The installation task
disables automatic reuse of the interactive gh login for public downloads; an
expired personal token must not block provisioning.

`development_macos_job_environment` is shared by Ansible's installation and
verification tasks and the runner's `config.toml` environment. It puts the
managed gem and Ruby binaries before system binaries and explicitly sets
`GEM_HOME`, `GEM_PATH`, and a UTF-8 locale for Fastlane testing notes. GitLab
exports these after starting the login shell,
so the job does not depend on shell profile initialization or launchd's PATH.
An ordinary SSH shell can still report Apple's system Ruby; the CI environment
is the one that must use Ruby 3.4 and the application's locked Bundler.

The mise path, Ruby version, gem directory, Bundler version, and PATH components
are configured in [defaults/main.yml](defaults/main.yml). The runtime path and
verification follow the pinned version automatically. When changing Ruby release
lines, also update the gem directory to avoid reusing incompatible gems.
Never install gems into Apple's system Ruby.

## Deploy and verify

Prerequisites are the existing Homebrew installation, Xcode account/keychain,
and `gitlab_runner_macos_auth_token` in the ignored encrypted
`group_vars/development_macos/vault.yml`. Keep that token unchanged. App Store
Connect API credentials belong in the application's protected GitLab variables,
not in this role.

From the repository root:

```sh
make check
git diff --check
make -C deploy deploy STACK=development_macos EXTRA_ARGS='--limit mac-mini --check'
make -C deploy deploy STACK=development_macos EXTRA_ARGS='--limit mac-mini'
```

Config changes notify the existing runner restart handler. Deploy when the
runner has no active jobs. The role verifies Ruby compatibility and the exact
Bundler version under the job environment. Run the deployment a second time;
it should report `changed=0` once packages and configuration are converged.
Check mode skips executable checks and, on a fresh host, skips Bundler installation
until Ruby exists.

After deploying, retry the failed application job and verify its result. For
Pixillate, retry only `testflight-distribute` if upload already succeeded; this
reuses the uploaded version/build and does not create a second upload.
