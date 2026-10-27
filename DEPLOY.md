# Deploying to the household Mac mini

Production runs on the Mac mini at `https://maggies-mac-mini.taild62a1b.ts.net:8445`, reachable only on the
Tailscale network. This is how it's set up, how to deploy a new version, and how to roll one back.

**How it runs**

- The container is `mealie-household-mealie-1`, from `compose.household.yml` in the main checkout
  (`~/Developer/mealie-household`). It runs the image `mealie-household:local`, bound to `127.0.0.1:9925`.
- Data lives in the named volume `mealie-household_mealie-household-data`: the SQLite database, the app's secrets,
  and the push notification key (`.vapid_private.pem`). Compose names the volume after the checkout's folder,
  so always run Compose from that folder.
- The main checkout's untracked `.env` holds the settings Compose reads:

  ```dotenv
  MEALIE_BIND_IP=127.0.0.1
  MEALIE_BASE_URL=https://maggies-mac-mini.taild62a1b.ts.net:8445
  ```

- Tailscale Serve publishes HTTPS port 8445 to `http://127.0.0.1:9925`. Other apps use the mini's other Serve
  ports (Field Theory has 443), so never reset Serve. Check it with
  `/Applications/Tailscale.app/Contents/MacOS/Tailscale serve status`.
- Docker Desktop starts at login, and the mini doesn't sleep while its display is off.

**Deploying**

Deploy only a merged `household-groceries`.

1. Tag the running image so it can come back, and name the tag after the change:

   ```bash
   docker tag "$(docker inspect -f '{{.Image}}' mealie-household-mealie-1)" mealie-household:pre-<change>
   ```

2. Build from a clean worktree. The image includes a source archive of everything in the build folder,
   untracked files included, so don't build from a checkout with work in progress:

   ```bash
   git fetch origin
   git worktree add --detach /tmp/mealie-deploy origin/household-groceries
   cd /tmp/mealie-deploy && docker build -f docker/Dockerfile -t mealie-household:local .
   ```

3. From the main checkout, stop the app and back up the volume while nothing is writing to it:

   ```bash
   docker compose -f compose.household.yml stop
   docker run --rm --entrypoint tar \
     -v mealie-household_mealie-household-data:/data:ro -v "$HOME/mealie-household-backups:/backup" \
     mealie-household:pre-<change> czf /backup/mealie-data-$(date +%F)-before-<change>.tgz -C /data .
   ```

4. Start the new version, which runs any database migrations on startup:

   ```bash
   docker compose -f compose.household.yml up -d
   ```

5. Check it: container health, `docker logs` for errors, `/api/app/about`, `/manifest.webmanifest` and `/sw.js`
   at the HTTPS address, and the app on a phone. Then remove the worktree with
   `git worktree remove /tmp/mealie-deploy`.

**Rolling back**

If the new version added a migration, the older image can't start on the newer database. First downgrade
with the new image still running, to the revision the older version expects:

```bash
docker exec -w /opt/mealie/lib/python3.14/site-packages/mealie/alembic mealie-household-mealie-1 \
  alembic downgrade <previous-revision>
```

Then switch back:

```bash
docker tag mealie-household:pre-<change> mealie-household:local
docker compose -f compose.household.yml up -d
```

If a downgrade isn't possible, stop the app and restore the backup tarball into the volume instead.
Never run `docker compose down -v`: it deletes the data volume.

Keep the newest rollback tag. Older ones can't run on the current database, so delete them
(`docker image rm mealie-household:pre-<old>`).

**Accounts**

A new database starts with one admin, `changeme@example.com` / `MyPassword`, and Mealie shows its setup wizard
after every sign-in until that account's email changes. Go through the wizard to set your own details.
Signup is off (`ALLOW_SIGNUP=false`), so add people with an invite link from the profile page
(**Get Invite Link**), or as an admin.

Each person turns notifications on per device: open the Home Screen app, go to **Messages**, tap
**Turn on notifications**, then **Send a test**. See [HOUSEHOLD_GROCERIES.md](HOUSEHOLD_GROCERIES.md#messages).
