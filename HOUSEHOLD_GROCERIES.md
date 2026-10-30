# Household Groceries for Mealie

A personal Mealie v3.28.0 fork for a household that shops at Walmart, Cub Foods, Aldi, and Whole Foods.
Upstream base: `0552eaa4a80031b8572849cca0ed95d07f1be001`.

## Run with Docker

Install Docker with Compose, extract this source package, and run from its root:

```bash
docker compose -f compose.household.yml up -d --build
```

Open `http://localhost:9925`. On a new installation, Mealie's initial account is
`changeme@example.com` / `MyPassword`. Change its password on first login.
Set `MEALIE_BASE_URL` in a `.env` file next to `compose.household.yml` to the address your household will
actually use (see below). The time zone defaults to America/Chicago.

Use Mealie's admin interface or household invitation flow to put family members in the same
**group and household**. Public registration is disabled in the supplied Compose configuration.
Grant Mealie's **Organize** permission to members who will create new ingredient Foods.
Members without that permission can select existing ingredients and save their product preferences.
Recipes, imports, authentication, backups, planner rules, and the standard shopping list interface remain available.

The named Docker volume stores all recipes, preferences, users, and grocery lists.
The supplied configuration uses Mealie's SQLite database; no separate database server is needed.
Use Mealie's existing backup feature before moving an established installation onto this fork.

## Home hosting and phone access

For household testing, run this Docker Compose project on an always-on home computer or NAS,
with Tailscale installed on that host and each phone. Tailscale Serve gives the app a private HTTPS
address that works on home Wi-Fi and mobile data. The Personal plan currently includes up to six
users for free; see [Tailscale pricing](https://tailscale.com/pricing).

Install Docker with Compose on the host and put this checkout there. Install and sign in to
Tailscale on the host and phones, and enable MagicDNS and HTTPS certificates in its admin console.
See [Tailscale HTTPS setup](https://tailscale.com/docs/how-to/set-up-https-certificates).
On NAS devices, install Tailscale using its instructions for your NAS model.

On a Mac mini, install [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/)
for its Intel or Apple silicon processor, open Docker, and finish its initial setup.
Enable Docker's start-at-login setting and keep that macOS user signed in.
Enable [Prevent automatic sleeping when the display is off](https://support.apple.com/guide/mac-help/mchle41a6ccd/mac)
in System Settings so the phone can reach the app while you are away.
After a reboot, verify Docker and Tailscale are running before testing phone access.

Start the app and then its HTTPS proxy on the same host. These commands use HTTPS port `8443`, so an existing
service on the host's default HTTPS port can keep running. Check `tailscale serve status` first; if `8443` is
already used, choose another free HTTPS port and include that same port in `MEALIE_BASE_URL`.
(The household's own install uses `8445`; [DEPLOY.md](DEPLOY.md) describes it.)

```bash
MEALIE_BIND_IP=127.0.0.1 docker compose -f compose.household.yml up -d --build
tailscale serve --bg --https=8443 http://127.0.0.1:9925
tailscale serve status
```

If the `tailscale` command is unavailable on macOS, use the CLI included in the application,
`/Applications/Tailscale.app/Contents/MacOS/Tailscale`.

Serve reports an address such as `https://your-host.your-tailnet.ts.net:8443`. Put the actual address
and the bind setting in the project's `.env` file so they survive future Compose commands:

```dotenv
MEALIE_BIND_IP=127.0.0.1
MEALIE_BASE_URL=https://your-host.your-tailnet.ts.net:8443
```

Run `docker compose -f compose.household.yml up -d` again to apply the address.
Use the full HTTPS address on your phone with Tailscale connected. No router port forwarding
or purchased domain is needed. [Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
handles the certificate and limits access to your Tailscale network.

Mealie already includes a web app manifest and service worker in its production build.
On iPhone, open the HTTPS address in Safari and choose Share → Add to Home Screen.
On Android, open it in Chrome and choose Install app or Add to Home screen.
[PWA installation requires HTTPS](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable)
when accessing another device; an ordinary `http://192.168...` LAN address does not meet that requirement.
Shopping changes still require a connection to the host; the home-screen app does not queue offline purchases.

Use Mealie's backup interface before updates, and copy downloaded backups off the host.
The named volume persists data when the app is rebuilt or restarted. Keep the same Compose project directory
when updating, and do not use `docker compose down -v`, which deletes its data volume.

## First use

1. Import or enter recipes in Mealie. Parse/link recipe ingredients to Foods in the recipe editor;
   preferred products are matched by Food ID, rather than by an approximate ingredient name.
2. Open **Groceries → Preferred products**. Start with your most common products.
3. Paste the product's link from the store, or scan its barcode (**Scan a product**). The name, store,
   package size, ingredient and a photo fill themselves in; check them over and save. See
   [Scanning](#scanning) and [Product photos](#product-photos).
4. Add alternatives for the same ingredient and mark them as backup choices.
5. The package size is optional. A 1 lb pack uses quantity `1`, unit `lb`; a gallon is `128` `fl oz`.
6. Plan dinners and sides in Mealie's calendar. Open Groceries and choose the week and stores you will visit.
7. Generate the list. Use store filters, open product links, and check off purchases.

Products with no saved URL work for in-store shopping. Ingredients without a matching product stay visible
under Unassigned. Saved preferences don't put every catalog product on your shopping list; pick the ones you
need from **Common items**.

## Behavior

### Store and product choices

An explicit product override wins, followed by an explicit store override, followed by the best enabled
product at an active store. Lower preference numbers win; equal priorities use the order of the selected stores.
Changing a card's assignment applies only to that week's items. Edit the catalog to change future defaults.

Links are saved bookmarks. This version does not fetch retailer prices, check stock, or fill carts.
A pasted link is read from its own address, which names the product and usually its size: store pages
turn automated readers away, so they're never fetched.

### Scanning

**Scan a product** on Preferred products, and the barcode button on the Out of list, open the phone's
camera. Pointing it at a barcode reads it straight away; the shutter takes a photo of the front of the
package instead. **Photo** reads a picture from the library, and **Type it** takes the numbers under the
barcode, for when the camera isn't allowed.

- A barcode is looked up in [Open Food Facts](https://world.openfoodfacts.org), a free product database
  that knows the store brands here (Great Value, Cub, Friendly Farms, 365). Only the number is sent.
- A barcode it doesn't know can be followed by a photo of the front, which the household's AI reads. That
  needs an AI provider that reads images. Photos go to that provider, as recipe photos do.
- Store brands set the store; other brands keep the store you'd chosen.
- Products remember their barcode. Scanning one already saved finds it, and a product saved from a link
  without one is recognized by its name ("This looks like your …") so its barcode can be remembered.

On the Out of list, scanning a saved product adds its ingredient at once, at that product's store, with
an Undo. Anything else asks first, and offers to save it as a preferred product, so the next scan is
instant. Barcodes are read on the phone itself, with ZXing compiled to WebAssembly (Safari can't read
barcodes on its own), served by Mealie rather than a CDN.

### Product photos

Preferred products have a photo of the package, shown on the products page and beside the item on the
shopping list, so the right one is easy to spot on the shelf. Tapping a photo shows it large. A product
gets the best photo there is, as soon as its link is pasted or its package scanned:

- The store's own photo, from the product's page, for a product with a store link. Each store keeps it
  somewhere else (Walmart in its link preview, Cub and Whole Foods in the page's product data, Aldi in
  the image its page loads first). Stores turn robots away now and then, so a page that comes back
  without a photo is fetched again, and a link that still gives none can be tried later from the form.
- The front of the package from Open Food Facts, for a scanned product. These are shoppers' photos.
- The photo snapped of the package, when a barcode nothing knew was identified from it.
- Any photo taken or picked in the form, which nothing replaces on its own.

A scanned product is also looked for at its store, so it gets the store's link and photo without
anyone pasting one. Stores don't answer a server's searches (Walmart's search shows robots a check, and
the others build their results in the browser), so the household's AI searches the web for the product's
page, with Codex's own search; this needs the ChatGPT provider, and Codex's `codex-code-mode-host`
installed beside `codex` (the Docker image has both), without which Codex offers the model no tools. Each page it names is opened and checked
first: it has to carry the scanned barcode, as Walmart's and Cub's do, or name the same brand, product and
size. Where a store's address doesn't name the brand, as Aldi's don't, the AI also looks at the photo:
stores keep a renamed product's old photo (Aldi's Millville granola still has a page showing the bag from
when it was Simply Nature), so a photo of another brand's package is passed over, for a better page or
for none. The form shows "Looking for it at Walmart…" and fills in the link and photo when it's found, about
10 to 20 seconds after the scan. A product saved before then, or saved from the Out of list, is filled in
by the server afterwards; searches for the same product are shared, and kept for a day. A link someone
gave or took off, and a photo someone chose, are never replaced.

The store's photo replaces Open Food Facts' or a snapshot when a link is added later. Photos are copied
to Mealie's data folder (`groceries/` under the data directory) at two sizes, served only to the
household, and included in backups. A photo found for a product that's never saved is cleared away
after a day, and a deleted product's photo with it.

### Quantities and repeat updates

Ingredient aggregation and recipe references use Mealie's existing shopping-list service.
Package quantities are rounded up **after** combining the week's matching requirements, including manual additions.
Package and pantry conversions require compatible standardized units. There are no guessed mass-to-volume conversions.
Count-based products require recipes to count the same item. Unspecified or incompatible quantities are flagged for review.

Each household has one managed shopping list per Monday-based week. Generation reconciles derived demand
instead of adding the same recipes again. Manual additions and trip overrides are preserved. Checked rows
remain purchased; a larger plan creates only the additional demand. Checking a card with a calculated package
count means you bought that suggested package count, so package overage is available to later updates in the same week.
Uncheck the card if the purchase was not completed.

Recipe multipliers apply to the recipe as written. Use `0` to omit purchasing for an entry, such as a leftover meal.
Only dinners and sides are included automatically. Other household needs can be manual items or weekly staples.

### Pantry and weekly staples

An exact pantry amount overrides Mealie's all-or-nothing on-hand flag for that food.
Pantry amounts are starting-inventory snapshots, not a continuously consumed inventory ledger.
They refresh when generating a week before shopping starts. Once items have been purchased, that week retains
its original pantry baseline, preventing updated pantry quantities from counting those same purchases twice.
Later pantry edits apply to future weeks. Update pantry quantities yourself after shopping or cooking.

A minimum weekly staple brings recipe requirements up to the saved weekly total. An extra weekly staple
adds that amount to recipe requirements. Pantry is deducted once after combining these requirements.

### Out of list

The Out of list is for things the household has run out of, whether or not a recipe uses them. Type them
into **We're out of…** on the This week or Groceries page, scan the empty package (see
[Scanning](#scanning)), or tell the assistant. Each item goes on the
newest grocery list for this week or later and stays there until someone checks it off. If there's no such
list yet, it waits and joins the next list you make. A newer list picks up anything still not bought.

An item whose name matches an ingredient (by name, plural, or alias) is linked to it, so it uses your
preferred products and stores and shares a card with any recipe demand for the same ingredient. Without an
amount it means one of whatever you usually buy, so a product with a package size counts at least one
package. Checking the row off on any list, including Mealie's standard shopping list, marks the item bought;
deleting the row from a list removes it from the Out of list. Bought items stay under **Bought lately** for
two weeks, where one tap adds them again.

### Common items

**Common items**, next to **We're out of…**, opens a list of every ingredient with an enabled preferred
product, grouped by aisle (the ingredient's label). Tap a row to put it on the list, and tap it again to take it
back off. Rows go on the Out of list, so they follow its rules: they go on the newest list for this week or
later, or wait for the next one, and they're never listed twice. Each row shows the product the list would
buy, and **Already on the list** when a recipe, staple, or addition has put it there already.

Choosing a store shows only what that store sells, with that store's product, and adding from it buys the item
there. Otherwise the list chooses the store, as it does for recipes. The one exception is an item whose stores
aren't on this week's trip. It goes on at the store its row shows rather than under Unassigned. When the search
finds nothing, you can add what you typed as a one-off.

To add or remove common items, save or turn off products in Preferred products. Things that aren't food, like
paper towels, need an ingredient for their product. Members with Organize permission can create one from the
product form.

### Ask (the kitchen assistant)

With a default AI provider set in group settings, **Ask** in the navigation opens a chat that keeps the Out of
list and answers questions about the grocery list, the meal plan, and your recipes. It can also suggest and
plan dinners. It uses tool calling through either an API-key provider or a ChatGPT subscription provider, and
its tools act only on the signed-in member's household.

### Messages

**Messages** in the navigation is one shared conversation for everyone in the household, for notes like
"we're out of milk" or "tacos on Thursday?". The open page checks for new messages every 5 seconds, and the
tab shows how many you haven't read. You can delete your own messages: tap one, then **Delete**.

Each device can also get a notification for each new message. On an iPhone or iPad (iOS 16.4 or later),
this only works in the Home Screen app: add Mealie to the Home Screen, open it from there, go to Messages and
tap **Turn on notifications**. **Send a test** checks the device. The Home Screen icon shows the unread count.
Notifications go through each browser's push service (Apple's, for iPhones), so the host needs internet access.
They show the sender's name and the start of the message.

The server signs notifications with a key it creates on first use, kept in the data volume as
`.vapid_private.pem`. Volume backups include it. If the key is lost, each device has to turn notifications on
again. Apple requires a contact for the server. By default that is the host of an https `BASE_URL`, or
`SMTP_FROM_EMAIL`. Set `WEB_PUSH_SUBJECT` (`mailto:you@example.com` or an https URL) to choose another.

### Household collaboration

Product preferences, pantry/staple rules, and weeks are scoped to the authenticated household.
Food records remain group-scoped, as in stock Mealie. The grocery page refreshes every 12 seconds when no
form edits are pending. An optimistic revision check prevents one grocery-page session from silently replacing
another session's changes. The standard shopping list uses the same underlying items; checked items appear in both views.

### Recommendations

Dinner suggestions use existing planner rules for the requested date, recipe ratings, household on-hand ingredients,
and past planned dinners. Recipes already in the chosen week are omitted. The UI requests suggestions for the
week's Monday. History is described as planning history; it is not proof that a meal was cooked.
AI recipe imports remain Mealie's standard optional feature, configured in group settings.

## Development

Use Python 3.14, Node 24, pnpm 11, uv, Go Task, and the `json2ts` CLI from json-schema-to-typescript.
On Linux, building python-ldap also needs LDAP and SASL development headers.

```bash
uv sync --frozen --all-extras
cd frontend
pnpm install --frozen-lockfile
pnpm exec nuxt prepare
cd ..
task dev:generate
task py:lint
task py:mypy
uv run --frozen pytest tests/integration_tests/user_household_tests/test_groceries.py
```

The generated TypeScript API models are in `frontend/app/lib/api/types/grocery.ts`.
Do not edit generated files by hand. The repository's AGENTS.md describes the normal development workflow.

Production frontend output is `frontend/.output/public`. The Dockerfile builds it and packages it into Mealie.
For local production-style testing, set `STATIC_FILES` to that directory when starting the backend.
The source download is generated with:

```bash
uv run --no-project python dev/household/build_source_archive.py . mealie/household-source.zip
```

The Docker build runs this automatically. The Groceries page links to the corresponding-source download;
it requires a signed-in household user and contains source/build instructions without databases or credentials.

## Main extension points

- `mealie/db/models/household/grocery.py`: household products, pantry/staple rules, managed weeks, and the Out of list.
- `mealie/services/household_services/groceries.py`: routing, purchase quantities, pantry, reconciliation, suggestions,
  and keeping Out of items on the newest list (`_sync_restock`).
- `mealie/repos/repository_grocery.py`: scoped data access, revision checks, and atomic list/week writes.
- `mealie/routes/households/controller_groceries.py`: authenticated `/api/households/groceries` endpoints.
- `mealie/services/household_services/assistant.py`: the assistant's tools and prompt context;
  `mealie/services/openai/openai.py` (`OpenAIService.chat`) runs the tool-calling conversation for either provider type.
- `frontend/app/pages/household/groceries/`: shopping and catalog pages.
- `frontend/app/pages/household/assistant.vue`: the Ask page.
- `frontend/app/components/Domain/Grocery/`: product and pantry/staple editors, the Out of panel, and the
  Common items picker (`GroceryCommonItemsDialog.vue`, fed by `GroceryService.common_items`).
- `mealie/services/household_services/messages.py` and `mealie/services/web_push/web_push.py`: Messages and its
  push notifications, at `/api/households/messages`.
- `frontend/app/pages/household/messages.vue`, `frontend/app/composables/use-household-messages.ts` and
  `use-web-push.ts`: the Messages page, the unread count, and turning notifications on.
- `frontend/service-worker/sw.ts`: the app's service worker. It precaches the build and shows notifications.

The fork adds four Alembic migrations: the three grocery tables, ChatGPT subscription AI providers, the Out of
list, and messages with read markers and push subscriptions. When merging a later upstream release with new migrations,
check for multiple Alembic heads and create/test an Alembic merge revision when required.
Preferences live in household tables so a shared Food does not impose one household's preferred products on another.

## Validation

Each feature has integration tests in `tests/integration_tests/user_household_tests/` (groceries, the Out of
list, Common items, the assistant, Messages) and unit tests under `tests/unit_tests/`. They cover aggregation,
repeated generation, store fallbacks, overrides, package overage, pantry snapshots, recurring rules, manual
additions, validation, authentication, and isolation between households. Before each merge, the full backend
suite, the frontend tests, lint, and type checks run, and new migrations are upgraded, downgraded and re-upgraded
on SQLite. Migrations haven't been run against a live PostgreSQL server.

Full frontend type checking reports errors that are already in upstream v3.28.0; the fork's own files add none.
The production Docker image runs on the household Mac mini; [DEPLOY.md](DEPLOY.md) covers building and
checking it.

## License

Mealie and this fork use AGPL-3.0-only. LICENSE and the corresponding source are included.
