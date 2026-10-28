import { describe, expect, test, vi } from "vitest";
import { ref } from "vue";
import { nextCookbookName, useCookbookDraft } from "../use-cookbook-draft";
import type { CreateCookBook, ReadCookBook } from "~/lib/api/types/cookbook";

const nameFor = (n: number) => `Family Cookbook ${n}`;

function cookbook(name: string, position = 1): ReadCookBook {
  return { id: name, name, position, queryFilterString: "tags.id IN [\"1\"]" } as ReadCookBook;
}

function setup(existing: ReadCookBook[] = []) {
  const created: CreateCookBook[] = [];
  const create = vi.fn(async (data: CreateCookBook): Promise<ReadCookBook | null> => {
    created.push(data);
    return { ...cookbook(data.name), ...data } as ReadCookBook;
  });
  return { created, create, ...useCookbookDraft(ref(existing), nameFor, create) };
}

describe("nextCookbookName", () => {
  test("counts up from the number of cookbooks", () => {
    expect(nextCookbookName(nameFor, [])).toBe("Family Cookbook 1");
    expect(nextCookbookName(nameFor, [cookbook("Breakfast")])).toBe("Family Cookbook 2");
  });

  test("skips names that are already taken", () => {
    const existing = [cookbook("Family Cookbook 2"), cookbook("family cookbook 3")];
    expect(nextCookbookName(nameFor, existing)).toBe("Family Cookbook 4");
  });
});

describe("useCookbookDraft", () => {
  test("starting a cookbook doesn't create anything, however many times Create is clicked", () => {
    const { create, draft, start } = setup();

    const first = start();
    first.name = "Weeknights";
    const second = start();
    start();

    expect(create).not.toHaveBeenCalled();
    // clicking Create again carries on with the cookbook being filled in
    expect(second).toBe(first);
    expect(draft.value?.name).toBe("Weeknights");
  });

  test("discarding it leaves nothing behind, and the next one starts fresh", () => {
    const { create, discard, draft, start } = setup([cookbook("Breakfast", 4)]);

    start().name = "Weeknights";
    discard();
    expect(draft.value).toBeNull();

    const next = start();
    expect(next.name).toBe("Family Cookbook 2");
    expect(next.position).toBe(5);
    expect(create).not.toHaveBeenCalled();
  });

  test("it can't be saved without a filter", async () => {
    const { create, save, start } = setup();
    start();

    expect(await save()).toBeNull();
    expect(create).not.toHaveBeenCalled();
  });

  test("saving creates it once, even when Save is pressed twice", async () => {
    const { created, draft, save, start } = setup();
    const target = start();
    target.queryFilterString = "tags.id IN [\"1\"]";

    const [first, second] = await Promise.all([save(), save()]);

    expect(created).toEqual([
      { name: "Family Cookbook 1", description: "", position: 1, public: false, queryFilterString: "tags.id IN [\"1\"]" },
    ]);
    expect(first?.name).toBe("Family Cookbook 1");
    expect(second).toBeNull();
    expect(draft.value).toBeNull();
  });

  test("a failed save keeps the draft, so it can be saved again", async () => {
    const { create, draft, save, start } = setup();
    start().queryFilterString = "tags.id IN [\"1\"]";
    create.mockResolvedValueOnce(null);

    expect(await save()).toBeNull();
    expect(draft.value?.name).toBe("Family Cookbook 1");
  });
});
