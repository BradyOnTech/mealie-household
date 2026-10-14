# Mac mini deployment handoff

Deploy this private Mealie fork on Maggie's Mac mini for household testing, with phone access over Tailscale.
The backup and grocery quantity fixes are finished. The remaining work is to build and run the production
container on the mini, verify HTTPS and PWA access, and help the household sign in.

**Get the project onto the mini**

Use a GitHub account with access to [BradyOnTech/mealie-household](https://github.com/BradyOnTech/mealie-household).
With GitHub CLI installed and authenticated on the mini:

```bash
mkdir -p ~/Documents/code
cd ~/Documents/code
gh repo clone BradyOnTech/mealie-household
cd mealie-household
```

The default branch is `household-groceries`. If this checkout already exists, use `git status` first
and `git pull --ff-only` when the worktree is clean.
Open this folder as a project in Codex on the mini and paste the prompt below into a new chat.

**Prompt for the new chat**

```text
Read AGENTS.md, MAC_MINI_HANDOFF.md, and HOUSEHOLD_GROCERIES.md.
Deploy this project locally on this Mac mini using compose.household.yml and Docker Desktop.
I already use Tailscale. Set up private HTTPS access and verify that I can install the app
on my phone and use it away from home. Continue through build/startup failures until it works.
Field Theory already uses this mini's main Tailscale HTTPS address; inspect Serve configuration
and use a separate free HTTPS port (planned: 8443). Preserve Field Theory and other running apps.
Keep changes small. Ask me only for required login/system dialogs or missing information.
Give me the working URL and first-login instructions when ready.
```

**Deployment settings**

The mini was online at `maggies-mac-mini.taild62a1b.ts.net` on October 14, 2026.
Its default HTTPS address served Field Theory. Confirm the actual hostname and existing Serve configuration
on the mini before applying settings. This deployment has not been started yet.

Docker Desktop must be running, with its initial setup completed. Keep the Docker user signed in,
enable start at login, and prevent the mini from sleeping while its display is off.
No Python or frontend development dependencies are required on the host; Docker builds both parts.

After confirming that HTTPS port `8443` is free, create an untracked `.env` in the repository:

```dotenv
MEALIE_BIND_IP=127.0.0.1
MEALIE_BASE_URL=https://maggies-mac-mini.taild62a1b.ts.net:8443
```

Then run from the repository root:

```bash
docker compose -f compose.household.yml up -d --build
docker compose -f compose.household.yml ps
curl --fail http://127.0.0.1:9925/api/app/about
/Applications/Tailscale.app/Contents/MacOS/Tailscale serve status
/Applications/Tailscale.app/Contents/MacOS/Tailscale serve --bg --https=8443 http://127.0.0.1:9925
```

Inspect Serve status before the final command. Use a different port if needed, and update `MEALIE_BASE_URL`
to match. Do not reset Serve or replace the existing service on port `443`.
Keep the same Compose project directory so future updates reuse its named data volume.
Do not run `docker compose down -v`, which deletes that volume.

**Verify before calling deployment complete**

Confirm container health, login, `/manifest.webmanifest`, `/sw.js`, and the production frontend at the HTTPS URL.
Verify Field Theory still works at its original URL. On the phone, connect Tailscale, turn Wi-Fi off,
and test the HTTPS URL over mobile data. On iPhone use Safari → Share → Add to Home Screen.
Generate a grocery week and check an item from the installed app.

For a new database, the initial Mealie login is `changeme@example.com` / `MyPassword`.
Change the password, set the household's users, and use Mealie's backup interface before updates.
Keep a downloaded backup off the mini. The PWA needs a connection for shopping changes;
offline purchase syncing has not been implemented.

**What has already been validated**

The backup fix preserves grocery JSON fields and restores `week_start` as a date.
Grocery aggregation keeps weight and volume separate, including within a single recipe,
while compatible quantities still combine and round to packages correctly.

Six regression cases were added. All 133 relevant backend tests passed against disposable SQLite,
including the complete grocery backup/restore round trip, existing backup tests, shopping-list tests,
and unit-conversion tests. Backend Ruff checks and mypy passed. Compose configuration validates.
The current fixes have not yet been tested in a running Docker image or live PostgreSQL.
No frontend behavior or database schema changed in these fixes.

**Sources**

- [Project setup and usage](HOUSEHOLD_GROCERIES.md)
- [Docker Desktop on Mac](https://docs.docker.com/desktop/setup/install/mac-install/)
- [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [Tailscale CLI on macOS](https://tailscale.com/docs/reference/tailscale-cli?tab=macos)
