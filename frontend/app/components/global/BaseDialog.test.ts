import { mount } from "@vue/test-utils";
import { describe, expect, test, vi } from "vitest";
import BaseDialog from "./BaseDialog.vue";

vi.mock("~/composables/use-global-i18n", () => ({ useGlobalI18n: () => ({ t: (key: string) => key }) }));

function mountDialog(props: Record<string, unknown>) {
  return mount(BaseDialog, {
    props: { modelValue: true, ...props },
    global: {
      mocks: { $vuetify: { display: { xs: false } } },
      stubs: {
        // the dialog's own listeners, like Enter, land on the stub's root
        "v-dialog": { template: "<div class=\"dialog\"><slot /></div>" },
        "v-bottom-sheet": true,
        "BaseDialogContent": { template: "<div><slot /></div>" },
      },
    },
  });
}

describe("BaseDialog submitting on Enter", () => {
  test("submits when the submit button is enabled", async () => {
    const wrapper = mountDialog({ canSubmit: true });
    await wrapper.find(".dialog").trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("submit")).toHaveLength(1);
  });

  test("doesn't submit while the submit button is disabled", async () => {
    const wrapper = mountDialog({ canSubmit: true, submitDisabled: true });
    await wrapper.find(".dialog").trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("submit")).toBeUndefined();
  });

  test("doesn't confirm while the confirm button is disabled", async () => {
    const wrapper = mountDialog({ canConfirm: true, submitDisabled: true });
    await wrapper.find(".dialog").trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("confirm")).toBeUndefined();
  });
});
