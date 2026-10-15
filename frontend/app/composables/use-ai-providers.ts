import { useUserApi } from "~/composables/api";
import type { AIProviderCreate, AIProviderUpdate } from "~/lib/api/types/group";
import type { AIProviderPayload } from "~/lib/api/user/group-ai-providers";

export function useAIProviders() {
  const api = useUserApi();
  const loading = ref(false);

  async function getOne(id: string) {
    loading.value = true;
    try {
      return await api.aiProviders.getOne(id);
    }
    finally {
      loading.value = false;
    }
  }

  async function createOne(payload: AIProviderCreate) {
    loading.value = true;
    try {
      return await api.aiProviders.createOne(payload);
    }
    finally {
      loading.value = false;
    }
  }

  async function updateOne(id: string, payload: AIProviderUpdate) {
    loading.value = true;
    try {
      return await api.aiProviders.updateOne(id, payload);
    }
    finally {
      loading.value = false;
    }
  }

  async function deleteOne(id: string) {
    loading.value = true;
    try {
      return await api.aiProviders.deleteOne(id);
    }
    finally {
      loading.value = false;
    }
  }

  async function testOne(payload: AIProviderPayload) {
    return await api.aiProviders.testOne(payload);
  }

  async function testSavedOne(id: string, overrides?: AIProviderPayload) {
    return await api.aiProviders.testSavedOne(id, overrides);
  }

  async function startChatGPTLogin() {
    return await api.aiProviders.startChatGPTLogin();
  }

  async function getChatGPTLogin(id: string) {
    return await api.aiProviders.getChatGPTLogin(id);
  }

  async function cancelChatGPTLogin(id: string) {
    return await api.aiProviders.cancelChatGPTLogin(id);
  }

  return {
    loading: readonly(loading),
    getOne,
    createOne,
    updateOne,
    deleteOne,
    testOne,
    testSavedOne,
    startChatGPTLogin,
    getChatGPTLogin,
    cancelChatGPTLogin,
  };
}
