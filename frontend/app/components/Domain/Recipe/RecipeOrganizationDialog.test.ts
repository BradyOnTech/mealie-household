import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import RecipeOrganizationDialog from "./RecipeOrganizationDialog.vue";
import type { Recipe } from "~/lib/api/types/recipe";

const api = vi.hoisted(() => ({ previewOrganization: vi.fn(), applyOrganization: vi.fn(), refresh: vi.fn() }));
vi.mock("~/composables/api", () => ({ useUserApi: () => ({ bulk: api }) }));
vi.mock("~/composables/store", () => ({
  useTagStore: () => ({ actions: { refresh: api.refresh } }),
  useCategoryStore: () => ({ actions: { refresh: api.refresh } }),
  useToolStore: () => ({ actions: { refresh: api.refresh } }),
}));

const wrappers: VueWrapper[] = [];
const recipe = { id: "recipe-1", name: "Chicken", slug: "chicken" } as Recipe;

function suggestion(overrides = {}) {
  return {
    recipeId: "recipe-1", name: "Chicken", slug: "chicken", tags: ["Chicken", "Baked"],
    categories: ["Main Dish"], cuisines: ["Thai", "Asian"], tools: ["Oven"], error: false, ...overrides,
  };
}

function mountDialog(recipes = [recipe]) {
  const wrapper = mount(RecipeOrganizationDialog, {
    props: { modelValue: false, recipes },
    global: {
      mocks: { $globals: { icons: { tags: "tags" } } },
      stubs: {
        BaseDialog: {
          props: ["modelValue", "submitDisabled"], emits: ["submit", "update:modelValue"],
          template: `<section v-if="modelValue"><slot />
            <button class="apply" :disabled="submitDisabled" @click="$emit('submit')">Apply</button>
          </section>`,
        },
        VCardText: { template: "<div><slot /></div>" },
        VCard: { template: "<article><slot /></article>" },
        VAlert: { template: "<p role=alert><slot /></p>" },
        VProgressLinear: true,
        VCheckbox: {
          props: ["modelValue", "value", "label", "disabled"], emits: ["update:modelValue"],
          template: `<label><input type="checkbox" :disabled="disabled" :checked="modelValue.includes(value)"
            @change="$emit('update:modelValue', modelValue.includes(value)
              ? modelValue.filter(v => v !== value) : [...modelValue, value])" />{{ label }}</label>`,
        },
        VChip: {
          props: ["disabled"], emits: ["click:close"],
          template: `<button class="label" :disabled="disabled" @click="$emit('click:close')"><slot /></button>`,
        },
      },
    },
  });
  wrappers.push(wrapper);
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  api.previewOrganization.mockResolvedValue({ data: [suggestion()] });
  api.applyOrganization.mockResolvedValue({ response: { status: 200 } });
  api.refresh.mockResolvedValue(undefined);
});

afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()));

test("previews without applying, then applies exactly the reviewed labels", async () => {
  const wrapper = mountDialog();
  await wrapper.setProps({ modelValue: true });
  await flushPromises();
  expect(api.previewOrganization).toHaveBeenCalledWith(["chicken"]);
  expect(api.applyOrganization).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain("Cuisines");
  for (const name of ["Baked", "Asian"]) {
    await wrapper.findAll(".label").find(chip => chip.text() === name)!.trigger("click");
  }
  await wrapper.get(".apply").trigger("click");
  await flushPromises();
  expect(api.applyOrganization).toHaveBeenCalledWith([{
    recipeId: "recipe-1", tags: ["Chicken"], categories: ["Main Dish"], cuisines: ["Thai"], tools: ["Oven"],
  }]);
  expect(api.previewOrganization).toHaveBeenCalledTimes(1);
  expect(wrapper.emitted("applied")).toHaveLength(1);
});

test("allows recipes to be excluded and never selects failed previews", async () => {
  const wrapper = mountDialog([recipe, { ...recipe, slug: "second" }]);
  api.previewOrganization.mockResolvedValueOnce({ data: [suggestion()] })
    .mockResolvedValueOnce({ data: [suggestion({ recipeId: "recipe-2", name: "Second", error: true })] });
  await wrapper.setProps({ modelValue: true });
  await flushPromises();
  const inputs = wrapper.findAll("input");
  expect(inputs[1]!.attributes("disabled")).toBeDefined();
  await inputs[0]!.setValue(false);
  expect(wrapper.get(".apply").attributes("disabled")).toBeDefined();
  expect(api.applyOrganization).not.toHaveBeenCalled();
});

test("disables apply during preview and discards results after the dialog closes", async () => {
  let resolve: (value: unknown) => void = () => {};
  api.previewOrganization.mockReturnValue(new Promise(r => resolve = r));
  const wrapper = mountDialog();
  await wrapper.setProps({ modelValue: true });
  expect(wrapper.get(".apply").attributes("disabled")).toBeDefined();
  await wrapper.setProps({ modelValue: false });
  resolve({ data: [suggestion()] });
  await flushPromises();
  expect(wrapper.findAll("article")).toHaveLength(0);
  expect(api.applyOrganization).not.toHaveBeenCalled();
});

test("leaves the review open when apply fails", async () => {
  api.applyOrganization.mockResolvedValue({ response: { status: 403 } });
  const wrapper = mountDialog();
  await wrapper.setProps({ modelValue: true });
  await flushPromises();
  await wrapper.get(".apply").trigger("click");
  await flushPromises();
  expect(wrapper.get("[role=alert]").text()).toContain("Could not organize");
  expect(wrapper.emitted("applied")).toBeUndefined();
});

test("rejects oversized selections before making AI requests", async () => {
  const wrapper = mountDialog(Array.from({ length: 51 }, () => recipe));
  await wrapper.setProps({ modelValue: true });
  await flushPromises();
  expect(wrapper.get("[role=alert]").text()).toContain("50 recipes");
  expect(api.previewOrganization).not.toHaveBeenCalled();
});
