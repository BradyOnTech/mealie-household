export interface ThemeConfig {
  lightPrimary: string;
  lightAccent: string;
  lightSecondary: string;
  lightSuccess: string;
  lightInfo: string;
  lightWarning: string;
  lightError: string;
  darkPrimary: string;
  darkAccent: string;
  darkSecondary: string;
  darkSuccess: string;
  darkInfo: string;
  darkWarning: string;
  darkError: string;
}

/**
 * "Sunday Paper" palette: warm paper, ink, hairline rules, a tomato accent and sage for done states.
 * The semantic colors can still be overridden per install through the THEME_* settings; the paper
 * surfaces and editorial accents below are fixed so the design holds together.
 */
const paperPalette = {
  light: {
    "background": "#F6F1E7",
    "surface": "#FCF9F3",
    "surface-bright": "#FFFDF8",
    "surface-light": "#EFE8DB",
    "surface-variant": "#2A241D",
    "on-surface-variant": "#F6F1E7",
    "on-background": "#211C16",
    "on-surface": "#211C16",
    "ink": "#211C16",
    "ink-muted": "#72685B",
    "rule": "#E1D7C6",
    "tomato": "#B3432A",
    "sage": "#5D7253",
    "wash": "#F2DFD4",
  },
  dark: {
    "background": "#15120E",
    "surface": "#1D1914",
    "surface-bright": "#26211B",
    "surface-light": "#2A241D",
    "surface-variant": "#E9E1D2",
    "on-surface-variant": "#15120E",
    "on-background": "#F0E8DA",
    "on-surface": "#F0E8DA",
    "ink": "#F0E8DA",
    "ink-muted": "#A89D8C",
    "rule": "#352E25",
    "tomato": "#E57B5D",
    "sage": "#9DB28E",
    "wash": "#3B261F",
  },
} as const;

let __cachedTheme: ThemeConfig | undefined;

async function fetchTheme(): Promise<ThemeConfig | undefined> {
  const route = "/api/app/about/theme";

  try {
    const response = await fetch(route);
    const data = await response.json();
    return data as ThemeConfig;
  }
  catch {
    return undefined;
  }
}

export default defineNuxtPlugin(async (nuxtApp) => {
  nuxtApp.hook("vuetify:before-create", async ({ vuetifyOptions }) => {
    let theme = __cachedTheme;
    if (!theme) {
      theme = await fetchTheme();
      __cachedTheme = theme;
    }
    vuetifyOptions.theme = {
      defaultTheme: nuxtApp.$config.public.useDark ? "dark" : "light",
      variations: {
        colors: ["primary", "accent", "secondary", "success", "info", "warning", "error", "background"],
        lighten: 3,
        darken: 3,
      },
      themes: {
        light: {
          dark: false,
          colors: {
            ...paperPalette.light,
            primary: theme?.lightPrimary ?? "#211C16",
            accent: theme?.lightAccent ?? "#B3432A",
            secondary: theme?.lightSecondary ?? "#5D7253",
            success: theme?.lightSuccess ?? "#4F7A4A",
            info: theme?.lightInfo ?? "#3D6585",
            warning: theme?.lightWarning ?? "#A8701D",
            error: theme?.lightError ?? "#9F2D2D",
          },
          variables: {
            "border-color": "#211C16",
            "border-opacity": 0.14,
            "shadow-color": "#3B2A1A",
            "high-emphasis-opacity": 0.94,
            "medium-emphasis-opacity": 0.68,
            "disabled-opacity": 0.42,
            "hover-opacity": 0.05,
            "focus-opacity": 0.1,
            "theme-code": "#EFE8DB",
            "theme-on-code": "#211C16",
          },
        },
        dark: {
          dark: true,
          colors: {
            ...paperPalette.dark,
            primary: theme?.darkPrimary ?? "#F0E8DA",
            accent: theme?.darkAccent ?? "#E57B5D",
            secondary: theme?.darkSecondary ?? "#9DB28E",
            success: theme?.darkSuccess ?? "#8FB386",
            info: theme?.darkInfo ?? "#8DB4D4",
            warning: theme?.darkWarning ?? "#E0A84F",
            error: theme?.darkError ?? "#E2675F",
          },
          variables: {
            "border-color": "#F0E8DA",
            "border-opacity": 0.14,
            "shadow-color": "#000000",
            "high-emphasis-opacity": 0.94,
            "medium-emphasis-opacity": 0.66,
            "disabled-opacity": 0.42,
            "hover-opacity": 0.06,
            "focus-opacity": 0.12,
            "theme-code": "#2A241D",
            "theme-on-code": "#F0E8DA",
          },
        },
      },
    };
  });
});
