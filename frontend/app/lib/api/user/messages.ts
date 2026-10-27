import { BaseAPI } from "../base/base-clients";
import type {
  HouseholdMessageCreate, HouseholdMessageList, HouseholdMessageOut, HouseholdMessageReadIn,
  HouseholdMessageUnread, PushConfig, PushSubscriptionCreate, PushTestResult,
} from "~/lib/api/types/messages";

const base = "/api/households/messages";

export interface HouseholdMessageQuery {
  before?: string;
  after?: string;
  limit?: number;
}

export class HouseholdMessagesAPI extends BaseAPI {
  list(query: HouseholdMessageQuery = {}) { return this.requests.get<HouseholdMessageList>(base, query); }
  send(data: HouseholdMessageCreate) { return this.requests.post<HouseholdMessageOut>(base, data); }
  remove(id: string) { return this.requests.delete<HouseholdMessageOut>(`${base}/${id}`); }
  unread() { return this.requests.get<HouseholdMessageUnread>(`${base}/unread`); }
  markRead(data: HouseholdMessageReadIn = {}) { return this.requests.post<HouseholdMessageUnread>(`${base}/read`, data); }
  pushConfig(endpoint?: string) { return this.requests.get<PushConfig>(`${base}/push`, endpoint ? { endpoint } : {}); }
  subscribe(data: PushSubscriptionCreate) { return this.requests.post<PushConfig>(`${base}/push/subscriptions`, data); }
  // The request helper drops a delete's params, so the endpoint goes in the URL
  unsubscribe(endpoint: string) { return this.requests.delete<PushConfig>(`${base}/push/subscriptions?endpoint=${encodeURIComponent(endpoint)}`); }
  sendTest() { return this.requests.post<PushTestResult>(`${base}/push/test`, {}); }
}
