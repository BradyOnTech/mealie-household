/* tslint:disable */

/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

export interface HouseholdMessageCreate {
  text: string;
}
export interface HouseholdMessageList {
  items: HouseholdMessageOut[];
  hasOlder?: boolean;
  unread?: number;
}
export interface HouseholdMessageOut {
  id: string;
  userId: string;
  user: HouseholdMessageSender;
  text: string;
  createdAt: string;
}
export interface HouseholdMessageSender {
  id: string;
  username?: string | null;
  fullName?: string | null;
}
export interface HouseholdMessageReadIn {
  readAt?: string | null;
}
export interface HouseholdMessageSave {
  text: string;
  groupId: string;
  householdId: string;
  userId: string;
}
export interface HouseholdMessageUnread {
  unread?: number;
  lastMessage?: HouseholdMessageOut | null;
}
export interface PushConfig {
  publicKey: string;
  subscribed?: boolean;
}
export interface PushKeys {
  p256dh: string;
  auth: string;
}
export interface PushSubscriptionCreate {
  endpoint: string;
  keys: PushKeys;
}
export interface PushSubscriptionOut {
  userId: string;
  endpoint: string;
  p256dh: string;
  auth: string;
  userAgent?: string;
  id: string;
  createdAt?: string | null;
}
export interface PushSubscriptionSave {
  userId: string;
  endpoint: string;
  p256dh: string;
  auth: string;
  userAgent?: string;
}
export interface PushTestResult {
  sent?: number;
}
