import { mount } from "@vue/test-utils";
import { expect, test } from "vitest";
import RecipeSourceLink from "./RecipeSourceLink.vue";

function render(url: string | null) {
  return mount(RecipeSourceLink, {
    props: { url },
    global: {
      mocks: { $globals: { icons: { play: "play" } } },
      stubs: { VBtn: { template: "<a><slot /></a>" } },
    },
  });
}

test.each([
  "https://www.instagram.com/reel/video/?igsh=shared",
  "https://instagram.com/p/post/",
  "https://m.instagram.com/reel/video/",
])("opens the saved Instagram source in a new tab: %s", (url) => {
  const wrapper = render(url);
  const link = wrapper.get("a");
  expect(link.text()).toBe("Watch on Instagram");
  expect(link.attributes("href")).toBe(url);
  expect(link.attributes("target")).toBe("_blank");
  expect(link.attributes("rel")).toBe("noopener noreferrer");
  wrapper.unmount();
});

test.each([
  null, "", "not a URL", "javascript:alert(1)", "https://instagram.com.evil.test/reel/video/",
  "https://instagram.com@evil.test/reel/video/", "https://example.com/?source=instagram.com",
])("does not add an Instagram action for other sources: %s", (url) => {
  const wrapper = render(url);
  expect(wrapper.find("a").exists()).toBe(false);
  wrapper.unmount();
});
