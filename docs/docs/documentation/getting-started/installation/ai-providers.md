# AI Integration

:octicons-tag-24: v1.7.0

Mealie's AI integration enables several features and enhancements throughout the application. To enable AI features, you must have access to an AI provider (such as OpenAI). Mealie works with any OpenAI-compatible API.

## Configuration

To set up AI providers, visit your group settings.

[Group Settings Demo](https://demo.mealie.io/group){ .md-button .md-button--primary }

- To enable AI features at all, you *must* set a default provider (e.g. `gpt-5`). The first provider you add becomes the default automatically, and a ChatGPT subscription provider also becomes the image provider when there isn't one, since it can read images
- To enable image recognition features, such as creating a recipe from an image, configure a provider capable of image recognition (e.g. `gpt-5`)
- To transcribe videos that have no captions when importing them, configure a provider capable of audio transcriptions (e.g. `whisper-1`). Videos with captions don't need one

For most users, choosing an OpenAI model (such as `gpt-5`) and supplying the OpenAI API key is all you need to do. Note that while OpenAI has a free tier, it's not sufficiently capable for Mealie (or most other production use cases). For more information, check out [OpenAI's rate limits](https://platform.openai.com/docs/guides/rate-limits). If you deposit $5 into your OpenAI account, you will be permanently bumped up to Tier 1, which is sufficient for Mealie. Cost per-request is dependant on many factors, but Mealie tries to keep token counts conservative.

If you have another provider you'd like to use, such as Azure, you can configure Mealie to use that instead as long as it has an OpenAI-compatible API. For instance, a common self-hosted alternative to OpenAI is [Ollama](https://ollama.com/). To use Ollama with Mealie, set your `base_url` to `http://localhost:11434/v1` (where `http://localhost:11434` is wherever you're hosting Ollama, and `/v1` enables the OpenAI-compatible endpoints). Note that you *must* provide an API key, even though it is ultimately ignored by Ollama.

Note that some models are capable of handling multiple features (e.g. `gpt-5` can handle both normal chat requests and image recognition requests). You may configure one provider for multiple provider features.

While Mealie has prompts for each AI task, you can override these with your own prompts if you'd like. For more information, check out the [backend configuration](../installation/backend-config.md).

### Choosing a model and reasoning for each task

Under **Choices for each task**, any of Mealie's AI tasks can have its own provider, model and reasoning level: the household assistant (Ask), reading recipe sources, writing up recipes, finding and reading the recipes in a cookbook, parsing ingredients, translating recipes, and choosing organizers. A task you leave alone uses the default provider, and its images the image provider, exactly as before.

- These choices belong to the group, so every household in it shares them.
- A task's provider is only used for text. Tasks that read images (recipe sources and cookbooks) have a separate choice for images, and otherwise use the group's image provider; Mealie never sends images to a different provider on its own.
- A provider can also have a default reasoning level, which its tasks use unless they choose their own. Left alone, a ChatGPT provider reasons at `low`, and an API-key provider sends no reasoning setting at all, so the model's own default applies.
- More reasoning, or a bigger model, can help with messy pages, but it's slower and uses more of your plan's limits or API credits.
- For a ChatGPT provider, Mealie lists the models Codex knows about, along with the reasoning levels each one supports. Being listed isn't a promise your plan can use a model; if it can't, requests fail with a message saying so. You can always type a model name instead.
- For an API-key provider, type the model name your service uses. Mealie only sends `reasoning_effort` when you choose a level, and not every model or OpenAI-compatible service accepts it, in which case requests fail with the provider's error. The assistant also needs a model that supports function calling through Chat Completions.

### Using a ChatGPT subscription

Instead of an API key, a provider can use a ChatGPT plan (Plus, Pro, Business, and so on), so its requests count against the plan's usage limits rather than being billed as API usage. Nothing has to reach Mealie from OpenAI's site, so this works however Mealie is hosted.

1. **Allow sign-in with a code.** In ChatGPT, open **Settings → Security** and turn on **Device code authorization for Codex**. ChatGPT turns codes down until this is on, with "Sorry, something went wrong" on OpenAI's page. On a workspace plan (Business, Enterprise, Edu), a workspace admin has to allow it.
2. **Add the provider.** Click **Add AI provider**, choose **ChatGPT subscription**, and click **Get a sign-in code**.
3. **Enter the code.** Click **Copy code and open OpenAI**, sign in to ChatGPT if it asks, paste the code, and approve. You can do this on any device. Codes last 15 minutes.
4. **Save it.** Mealie notices the sign-in, checks the connection, and you click **Add**.

A few things to know:

- Requests go through the [Codex CLI](https://github.com/openai/codex), which the Docker image includes. Outside Docker, install it and, if it isn't on your `PATH`, set [`CODEX_BIN`](./backend-config.md#openai). Each request starts its own short-lived Codex process, which adds a second or so.
- It can read text and images, so it can be your default and image provider, and it can import videos from their captions. It can't transcribe audio, so to import videos that have no captions, use an API-key provider as your audio provider.
- Leave the model blank to use your plan's default model.
- Everyone in your group shares the one ChatGPT account and its usage limits. When those run out, AI features fail until the limit resets.
- The sign-in is stored in Mealie's database, the same way an API key is, and Codex refreshes it as needed. To switch accounts, edit the provider and sign in again.
- Mealie keeps a sign-in that's in progress in memory, so if you've raised `UVICORN_WORKERS` above 1, signing in may not complete reliably.

## AI Features
- The OpenAI Ingredient Parser can be used as an alternative to the NLP and Brute Force parsers. Simply choose the OpenAI parser while parsing ingredients (:octicons-tag-24: v1.7.0)
- When importing a recipe via URL, if the default recipe scraper is unable to read the recipe data from a webpage, the webpage contents will be parsed by AI (:octicons-tag-24: v1.9.0). A link to a video is read from the video instead (see [Videos](#videos))
- The **Import with AI** page creates a recipe out of just about anything: pasted text, HTML, or JSON, photos of a recipe, a link, or any combination of them (:octicons-tag-24: v3.23.0)
- The **Import a Cookbook (PDF or EPUB)** page imports every recipe in a cookbook PDF or EPUB, with their photos
- The **Ask** page is a chat with a kitchen assistant that can keep your household's Out of list and answer questions about its groceries, meal plan, and recipes

## Recipe organization

When AI is enabled, recipe imports can automatically choose categories, tags, and tools using the
**Organizer matching** task. This works for ordinary website imports as well as AI, bulk URL, PDF,
and EPUB imports. URL imports have an **Automatically organize this recipe** option; cookbook
imports have an **Add tags, categories, and tools to each recipe** option. Both default to enabled.
Classification uses one additional AI request per recipe. If it fails, the recipe is still imported.

The classifier prefers your group's existing labels and can create a small set of standard labels,
such as **Main Dish**, **Dessert**, **Chicken**, **Pasta**, and **Oven**. It can infer an obvious course,
main ingredient, or cooking method from the recipe. Dietary and cuisine labels require explicit
support, and **Quick** requires a total time of 30 minutes or less. The AI import page's
**Create new organizers** option allows additional names outside the standard vocabulary.

Importing a website's original categories or keywords remains a separate option. Those options
retain source labels, including names outside the standard vocabulary. Cookbook source notes and
the cookbook tag used for navigation are preserved.

To organize existing recipes, open **Group settings → Manage data → Recipes**, select up to 50
recipes, and choose **Organize with AI**. Review the suggestions, remove unwanted labels or uncheck
recipes, then apply. Preview does not save anything. Applying adds the accepted labels and preserves
existing labels and recipe edits. You must have permission to edit every selected recipe.

## Ask

The **Ask** page, in the main navigation once a default provider is set, is a chat for your household. Tell it what you've run out of ("we're out of rice and paper towels") and it adds those to the household's Out of list, which goes on the newest grocery list. You can also ask what's left on the grocery list, what's planned this week, or what's in a recipe, have it suggest or plan a dinner, and have it change, remove, or check off things on the Out of list.

The assistant works through tools that use the same permissions as the rest of the app, so it only sees and changes your own household's lists and plans, and the group's recipes you can see. It uses your default provider, through tool calling: any OpenAI-compatible API that supports tools works, and so does a ChatGPT subscription provider. The conversation is kept on your device, and each message sends the recent conversation along with it.

Its instructions are the `household.assistant` prompt, which you can override like any other prompt.

## Import with AI

The **Import with AI** page, found under *Create ➞ Import with AI*, creates a recipe from any combination of:

- **A URL.** Mealie fetches the page and reads the recipe from it. Give it a link to a video (e.g. YouTube or Instagram) and the recipe is read from the video instead (see [Videos](#videos)). The URL is always saved as the recipe's source.
- **Content.** Paste a recipe as plain text, or paste raw HTML or a [schema.org Recipe](https://schema.org/Recipe) JSON object. This is useful when a site blocks Mealie from reading it directly. It's also where you write notes about a recipe you're importing from somewhere else.
- **Images.** Upload one or more photos of a recipe, hand-written or typed. Multiple photos are treated as pages of a single recipe, and the first one becomes the recipe's image. This requires an image provider.

Every source you provide is read, and the results are combined into one description of the recipe. Content you paste alongside a URL, a video, or photos adds to them rather than replacing them, so a page that only partly loaded can be topped up by hand. Where your own content disagrees with the other sources it wins, so it doubles as a place for notes: what to name the recipe, a correction to an ingredient, a step the video skipped over. If content is the only thing you provide, it's simply the recipe's source material.

You can also optionally have the recipe translated into your own language.

### Videos

A video, whether you import it here or with *Import with URL*, is read from what it publishes about itself: its title, its description, and its captions. The video itself isn't downloaded, and no audio provider is needed, so a group whose only provider is a [ChatGPT subscription](#using-a-chatgpt-subscription) can import videos too.

- **Captions.** The creator's own captions are used if the video has them in the language it's spoken in, and otherwise the captions recognized from its speech, which YouTube has for most videos. Machine-translated captions are never used; to get a recipe in another language, have it translated instead.
- **Chapters.** A video split into chapters keeps them as headings in its transcript, which helps the recipe come out in sections.
- **The written recipe.** Cooking channels often link to a written version of the recipe from the description. When a link the description introduces as the recipe ("Full recipe: …") leads to a recipe whose name matches the video's title, that recipe is read too. Its ingredients come with exact amounts, where a video might only say "a splash", and its photo is used instead of the video's thumbnail.
- **No captions.** A video without captions has its audio transcribed by your audio provider, if you've configured one (videos over 90 minutes are skipped). Otherwise the recipe is read from the description, which works for the many short videos that write their recipe there.

Recipe sites that also publish videos, like NYT Cooking, are read from the recipe on their page rather than from the video.

### Organizers

Mealie asks AI which tags, categories, and tools the recipe refers to, and always matches what comes back against the organizers you already have, so an import doesn't create a near-duplicate of a tag you're already using.

Organizers that don't match anything you have are discarded, unless you check **Create new organizers**, in which case they're created for you.

Mealie only assigns an organizer that the recipe itself refers to. It won't guess a cuisine from the ingredients or a course from the kind of dish, so a bare list of ingredients and steps usually imports with no organizers at all.

### Which provider is used

Reading the source material is the only step that needs to understand images or audio, so that's the only step that uses your image or audio provider. Turning what it read into a recipe, and working out its organizers, use your default provider, unless you've [chosen another for that task](#choosing-a-model-and-reasoning-for-each-task).

This means an import with photos attached is read by your image provider even if you also pasted text alongside them.

## Import a Cookbook (PDF or EPUB)

The **Import a Cookbook (PDF or EPUB)** page, under *Create ➞ Import a Cookbook (PDF or EPUB)* or *Cookbooks ➞ Import from a PDF or EPUB*, imports every recipe in a cookbook PDF or EPUB at once. Give it the file and a name for the cookbook, and it runs in the background, listing each recipe as it's imported. You can leave the page while it works and come back to it.

The import happens in two passes:

1. **Finding the recipes.** The text of the PDF's pages goes to your default provider a couple of dozen pages at a time, and it lists each recipe and the pages it's on. Tables of contents, introductions, and section pages are skipped.
2. **Importing them.** Each recipe is read from the text of its pages, along with an image of each page if you've configured an image provider. Designed cookbooks often store their text out of reading order, so the page images let the AI see which heading, ingredient, and step goes where. Without an image provider, only the text is read.

Each recipe's photo is cut straight out of the PDF, cropped the way the page shows it, so photos are imported even without an image provider. Every recipe is tagged with the cookbook's name and gets a note saying which page it came from. Unless you turn it off, the cookbook is also added under **Cookbooks**, showing the recipes with its tag. You can optionally have tags, categories, and tools added to each recipe too, which takes one more AI request per recipe.

A PDF with no text in it, such as a scanned book, can still be imported if you have an image provider, since every page is then read from an image of it. That's slower, and takes more of your provider's usage.

An EPUB has no pages, so Mealie cuts it into page-sized pieces, starting a new one at each chapter and at each top-level heading, which is where cookbooks usually start a recipe. An EPUB's text is already in reading order, so no page images are sent with it, and each recipe's photo is the largest picture among its pages. The recipe's note names the book but not a page, since the pieces don't match any ebook reader's pages. EPUBs protected by DRM can't be imported.

### Large cookbooks and usage limits

Importing a cookbook takes one AI request per recipe, plus a few to find them, so a 100-recipe book is a little over 100 requests. A request that fails for a passing reason, like a dropped connection, is tried again once the rest are done. If your provider runs out partway through, for example because a [ChatGPT subscription](#using-a-chatgpt-subscription) reached its plan's usage limit, the import stops and says so.

Each imported recipe remembers which file and page it came from, so you can import the same file again to pick up where it left off: recipes that are already imported are skipped. The same goes for an import interrupted by Mealie restarting. If you delete an imported recipe, importing the file again brings it back.
