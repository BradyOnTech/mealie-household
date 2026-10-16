/* tslint:disable */

/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

export type AssistantRole = "user" | "assistant";

export interface AssistantAction {
  kind: string;
  summary: string;
}
export interface AssistantChatRequest {
  messages: [AssistantMessage, ...AssistantMessage[]];
}
export interface AssistantMessage {
  role: AssistantRole;
  content: string;
}
export interface AssistantChatResponse {
  reply: string;
  actions?: AssistantAction[];
}
