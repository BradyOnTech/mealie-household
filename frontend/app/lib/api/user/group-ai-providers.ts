import { BaseAPI } from "../base/base-clients";
import type {
  AIProviderCreate,
  AIProviderOut,
  AIProviderTestResult,
  AIProviderUpdate,
  ChatGPTLoginOut,
} from "~/lib/api/types/group";

/** Write-only fields, which the generated types leave out */
export type AIProviderPayload = AIProviderCreate & { apiKey?: string; chatgptLoginId?: string };

const prefix = "/api/groups/ai-providers";

const routes = {
  providers: `${prefix}/providers`,
  providersId: (id: string) => `${prefix}/providers/${id}`,
  providersTest: `${prefix}/providers/test`,
  providersIdTest: (id: string) => `${prefix}/providers/${id}/test`,
  chatgptLogin: `${prefix}/chatgpt-login`,
  chatgptLoginId: (id: string) => `${prefix}/chatgpt-login/${id}`,
};

export class AIProvidersAPI extends BaseAPI {
  async getOne(id: string) {
    return await this.requests.get<AIProviderOut>(routes.providersId(id));
  }

  async createOne(payload: AIProviderCreate) {
    return await this.requests.post<AIProviderOut>(routes.providers, payload);
  }

  async updateOne(id: string, payload: AIProviderUpdate) {
    return await this.requests.put<AIProviderOut, AIProviderUpdate>(routes.providersId(id), payload);
  }

  async deleteOne(id: string) {
    return await this.requests.delete<AIProviderOut>(routes.providersId(id));
  }

  async testOne(payload: AIProviderPayload) {
    return await this.requests.post<AIProviderTestResult>(routes.providersTest, payload);
  }

  async testSavedOne(id: string, overrides?: AIProviderPayload) {
    return await this.requests.post<AIProviderTestResult>(routes.providersIdTest(id), overrides);
  }

  async startChatGPTLogin() {
    return await this.requests.post<ChatGPTLoginOut>(routes.chatgptLogin, {});
  }

  async getChatGPTLogin(id: string) {
    return await this.requests.get<ChatGPTLoginOut>(routes.chatgptLoginId(id));
  }

  async cancelChatGPTLogin(id: string) {
    return await this.requests.delete(routes.chatgptLoginId(id));
  }
}
