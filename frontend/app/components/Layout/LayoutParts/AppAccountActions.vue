<template>
  <div class="app-account-actions">
    <AnnouncementDialog v-model="announcementsOpen" />
    <LanguageDialog v-model="languageOpen" />

    <div v-if="user && showHeader" class="app-account-actions__who">
      <AppInitialsAvatar :name="user.fullName || user.username || ''" size="40" />
      <div class="app-account-actions__who-text">
        <div class="app-account-actions__name">
          {{ user.fullName || user.username }}
        </div>
        <div class="app-account-actions__email">
          {{ user.email }}
        </div>
      </div>
    </div>

    <v-list density="comfortable" bg-color="transparent" class="py-0">
      <v-list-item
        v-for="link in accountLinks"
        :key="link.key"
        :to="link.to"
        :prepend-icon="link.icon"
        :title="link.title"
      />
      <v-divider v-if="accountLinks.length" class="my-1" />
      <v-list-item
        :prepend-icon="isDark ? $globals.icons.weatherSunny : $globals.icons.weatherNight"
        :title="isDark ? $t('settings.theme.light-mode') : $t('settings.theme.dark-mode')"
        @click="toggleDark"
      />
      <v-list-item
        :prepend-icon="$globals.icons.translate"
        :title="$t('sidebar.language')"
        @click="languageOpen = true"
      />
      <v-list-item
        v-if="loggedIn && announcementsEnabled"
        :title="$t('announcements.announcements')"
        @click="announcementsOpen = true"
      >
        <template #prepend>
          <v-badge
            :model-value="!!newAnnouncements.length"
            color="tomato"
            :content="newAnnouncements.length || undefined"
            offset-x="-2"
          >
            <v-icon :icon="$globals.icons.bullhornVariant" />
          </v-badge>
        </template>
      </v-list-item>
      <template v-if="loggedIn">
        <v-divider class="my-1" />
        <v-list-item
          :prepend-icon="$globals.icons.logout"
          :title="$t('user.logout')"
          @click="logout"
        />
      </template>
    </v-list>
  </div>
</template>

<script setup lang="ts">
import AnnouncementDialog from "~/components/Domain/Announcement/AnnouncementDialog.vue";
import AppInitialsAvatar from "~/components/Layout/LayoutParts/AppInitialsAvatar.vue";
import { useAnnouncements } from "~/composables/use-announcements";
import { useAppNavigation } from "~/composables/use-app-navigation";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import { useToggleDarkMode } from "~/composables/use-utils";

withDefaults(defineProps<{ showHeader?: boolean }>(), {
  showHeader: true,
});

const auth = useMealieAuth();
const user = computed(() => auth.user.value);
const { loggedIn } = useLoggedInState();
const { accountLinks } = useAppNavigation();
const { announcementsEnabled, newAnnouncements } = useAnnouncements();

const theme = useTheme();
const isDark = computed(() => theme.current.value.dark);
const toggleDark = useToggleDarkMode();

const languageOpen = ref(false);
const announcementsOpen = ref(false);

async function logout() {
  try {
    await auth.signOut("/login?direct=1");
  }
  catch (e) {
    console.error(e);
  }
}
</script>

<style scoped>
.app-account-actions__who {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px 12px;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}

.app-account-actions__who-text {
  min-width: 0;
}

.app-account-actions__name {
  font-family: var(--paper-serif);
  font-size: 1.0625rem;
  line-height: 1.2;
}

.app-account-actions__email {
  font-size: 0.8125rem;
  color: rgb(var(--v-theme-ink-muted));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
