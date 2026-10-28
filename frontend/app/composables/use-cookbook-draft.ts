import type { CreateCookBook, ReadCookBook } from "~/lib/api/types/cookbook";

/**
 * The first "<household> Cookbook <n>" name, counting up from one past the number of cookbooks, that
 * no cookbook has yet.
 */
export function nextCookbookName(nameFor: (n: number) => string, existing: { name: string }[]): string {
  const taken = new Set(existing.map(cookbook => cookbook.name.trim().toLowerCase()));

  let n = existing.length + 1;
  while (taken.has(nameFor(n).trim().toLowerCase())) {
    n++;
  }
  return nameFor(n);
}

/**
 * A new cookbook being filled in on the Cookbooks page. It only exists in the browser until it's
 * saved, so leaving the page, closing the tab or clicking Create again never leaves a half-made
 * cookbook behind, and saving it twice in a row creates it once.
 */
export function useCookbookDraft(
  existing: Ref<ReadCookBook[]>,
  nameFor: (n: number) => string,
  create: (data: CreateCookBook) => Promise<ReadCookBook | null>,
) {
  const draft = ref<ReadCookBook | null>(null);
  const saving = ref(false);

  function start(): ReadCookBook {
    // Create clicked again while a draft is open carries on with that draft
    if (draft.value) {
      return draft.value;
    }

    const positions = existing.value.map(cookbook => cookbook.position ?? 0);
    draft.value = {
      name: nextCookbookName(nameFor, existing.value),
      description: "",
      position: Math.max(0, ...positions) + 1,
      public: false,
      queryFilterString: "",
    } as ReadCookBook;
    return draft.value;
  }

  async function save(): Promise<ReadCookBook | null> {
    if (!draft.value?.queryFilterString || saving.value) {
      return null;
    }

    const { name, description, position, public: isPublic, queryFilterString } = draft.value;
    saving.value = true;
    try {
      const created = await create({ name, description, position, public: isPublic, queryFilterString });
      if (created) {
        draft.value = null;
      }
      return created;
    }
    finally {
      saving.value = false;
    }
  }

  function discard() {
    draft.value = null;
  }

  return { draft, saving, start, save, discard };
}
