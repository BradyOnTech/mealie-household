import { BaseAPI } from "../base/base-clients";
import type { AssistantChatRequest, AssistantChatResponse } from "~/lib/api/types/assistant";

export class AssistantAPI extends BaseAPI {
  chat(data: AssistantChatRequest) { return this.requests.post<AssistantChatResponse>("/api/households/assistant/chat", data); }
}
