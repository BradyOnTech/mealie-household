<template>
  <div v-if="items">
    <RecipeOrganizerDialog
      v-model="dialogs.organizer"
      :item-type="itemType"
    />

    <BaseDialog
      v-if="deleteTarget"
      v-model="dialogs.delete"
      bottom-sheet
      :title="$t('general.delete-with-name', { name: $t(translationKey) })"
      color="error"
      :icon="$globals.icons.alertCircle"
      can-confirm
      @confirm="deleteOne()"
    >
      <v-card-text>
        <p>{{ $t("general.confirm-delete-generic-with-name", { name: $t(translationKey) }) }}</p>
        <p class="mt-4 mb-0 ml-4">
          {{ deleteTarget.name }}
        </p>
      </v-card-text>
    </BaseDialog>

    <BaseDialog
      v-if="updateTarget"
      v-model="dialogs.update"
      :title="$t('general.update')"
      :icon="$globals.icons.edit"
      can-confirm
      @confirm="updateOne()"
    >
      <v-card-text>
        <v-text-field
          v-model="updateTarget.name"
          :label="$t('general.name')"
        />
        <v-checkbox
          v-if="itemType === Organizer.Tool"
          v-model="updateTarget.onHand"
          :label="$t('tool.on-hand')"
        />
      </v-card-text>
    </BaseDialog>

    <header class="organizer-head">
      <div>
        <span class="paper-kicker">{{ $t("general.recipes") }}</span>
        <h1 class="organizer-head__title paper-headline">
          <slot name="title" />
        </h1>
      </div>
      <BaseButton
        create
        @click="dialogs.organizer = true"
      />
    </header>
    <v-text-field
      v-model="searchString"
      rounded="pill"
      density="comfortable"
      autofocus
      hide-details
      class="organizer-search"
      :placeholder="$t('search.search-placeholder')"
      :prepend-inner-icon="$globals.icons.search"
      clearable
    />
    <section
      v-for="(itms, key, idx) in itemsSorted"
      :key="'header' + idx"
      :class="idx === 1 ? null : 'my-4'"
    >
      <BaseCardSectionTitle
        v-if="isTitle(key)"
        :title="key"
      />
      <v-row>
        <v-col
          v-for="(item, index) in itms"
          :key="'cat' + index"
          cols="12"
          :sm="12"
          :md="6"
          :lg="4"
          :xl="3"
        >
          <v-card
            v-if="item"
            flat
            color="transparent"
            class="organizer-item"
            :to="`/g/${groupSlug}?${itemType}=${item.id}`"
          >
            <v-card-actions class="px-0">
              <v-card-title class="organizer-item__name py-1 px-0 text-truncate flex-shrink-1 flex-grow-1">
                {{ item.name }}
              </v-card-title>
              <ContextMenu
                :items="[presets.delete, presets.edit]"
                @delete="confirmDelete(item)"
                @edit="openUpdateDialog(item)"
              />
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>
    </section>
  </div>
</template>

<script setup lang="ts">
import Fuse from "fuse.js";
import { useContextPresets } from "~/composables/use-context-presents";
import RecipeOrganizerDialog from "~/components/Domain/Recipe/RecipeOrganizerDialog.vue";
import { Organizer, type RecipeOrganizer } from "~/lib/api/types/non-generated";
import { useRouteQuery } from "~/composables/use-router";
import { deepCopy } from "~/composables/use-utils";

interface GenericItem {
  id: string;
  name: string;
  slug: string;
  onHand: boolean;
}

const props = defineProps<{
  items: GenericItem[];
  icon: string;
  itemType: RecipeOrganizer;
}>();

const emit = defineEmits<{
  update: [item: GenericItem];
  delete: [id: string];
}>();

const state = reactive({
  // Search Options
  options: {
    ignoreLocation: true,
    shouldSort: true,
    threshold: 0.2,
    location: 0,
    distance: 20,
    findAllMatches: true,
    maxPatternLength: 32,
    minMatchCharLength: 1,
    keys: ["name"],
  },
});

const auth = useMealieAuth();
const route = useRoute();
const groupSlug = computed(() => route.params.groupSlug as string || auth.user?.value?.groupSlug || "");

// =================================================================
// Context Menu

const dialogs = ref({
  organizer: false,
  update: false,
  delete: false,
});

const presets = useContextPresets();

const translationKey = computed<string>(() => {
  const typeMap = {
    categories: "category.category",
    tags: "tag.tag",
    tools: "tool.tool",
    foods: "shopping-list.food",
    households: "household.household",
  };
  return typeMap[props.itemType] || "";
});

const deleteTarget = ref<GenericItem | null>(null);
const updateTarget = ref<GenericItem | null>(null);

function confirmDelete(item: GenericItem) {
  deleteTarget.value = item;
  dialogs.value.delete = true;
}

function deleteOne() {
  if (!deleteTarget.value) {
    return;
  }

  emit("delete", deleteTarget.value.id);
}

function openUpdateDialog(item: GenericItem) {
  updateTarget.value = deepCopy(item);
  dialogs.value.update = true;
}

function updateOne() {
  if (!updateTarget.value) {
    return;
  }

  emit("update", updateTarget.value);
}

// ================================================================
// Search Functions

const searchString = useRouteQuery("q", "");

const fuse = computed(() => {
  return new Fuse(props.items, state.options);
});

const fuzzyItems = computed<GenericItem[]>(() => {
  if (searchString.value.trim() === "") {
    return props.items;
  }
  const result = fuse.value.search(searchString.value.trim() as string);
  return result.map(x => x.item);
});

// =================================================================
// Sorted Items

const itemsSorted = computed(() => {
  const byLetter: { [key: string]: Array<GenericItem> } = {};

  if (!fuzzyItems.value) {
    return byLetter;
  }

  [...fuzzyItems.value]
    .sort((a, b) => a.name.localeCompare(b.name))
    .forEach((item) => {
      const letter = item.name[0].toUpperCase();
      if (!byLetter[letter]) {
        byLetter[letter] = [];
      }
      byLetter[letter].push(item);
    });

  return byLetter;
});

function isTitle(str: number | string) {
  return typeof str === "string" && str.length === 1;
}
</script>

<style scoped>
.organizer-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px 24px;
  margin: 16px 0 20px;
}

.organizer-head__title {
  margin: 6px 0 0;
  font-size: 2.75rem;
}

.organizer-search {
  max-width: 560px;
  margin-bottom: 8px;
}

.organizer-item {
  border-bottom: 1px solid rgb(var(--v-theme-rule));
  border-radius: 0;
}

.organizer-item__name {
  font-size: 1.1875rem;
}

@media (max-width: 599px) {
  .organizer-head__title {
    font-size: 2.125rem;
  }
}
</style>
