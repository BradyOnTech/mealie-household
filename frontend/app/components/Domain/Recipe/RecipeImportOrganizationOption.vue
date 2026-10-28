<template>
  <v-checkbox
    v-if="group?.aiProviderSettings?.aiEnabled"
    v-model="enabled"
    :label="$t('recipe.organize-on-import')"
    :hint="$t('recipe.organize-on-import-hint')"
    persistent-hint
    :disabled="disabled"
    color="primary"
  />
</template>

<script setup lang="ts">
import { useGroupSelf } from "~/composables/use-groups";

defineProps<{ disabled?: boolean }>();
const enabled = defineModel<boolean>({ default: true });
const { group } = useGroupSelf();
</script>
