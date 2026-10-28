/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

export type AIProviderType = "openai" | "chatgpt";
export type AITask =
  | "household_assistant"
  | "recipe_source_reading"
  | "recipe_building"
  | "cookbook_discovery"
  | "cookbook_extraction"
  | "ingredient_parsing"
  | "recipe_translation"
  | "organizer_matching";
export type ChatGPTLoginState = "waiting" | "connected" | "failed" | "expired";
export type SupportedMigrations =
  | "nextcloud"
  | "chowdown"
  | "copymethat"
  | "paprika"
  | "mealie_alpha"
  | "tandoor"
  | "plantoeat"
  | "myrecipebox"
  | "recipekeeper"
  | "cookn";

export interface AIModelCatalog {
  discovered: boolean;
  models?: AIModelOption[];
  message?: string | null;
}
export interface AIModelOption {
  model: string;
  displayName: string;
  description?: string | null;
  isDefault?: boolean;
  defaultReasoningEffort?: string | null;
  supportedReasoningEfforts?: AIReasoningEffortOption[];
  inputModalities?: string[];
}
export interface AIReasoningEffortOption {
  effort: string;
  description?: string | null;
}
export interface AIProviderCreate {
  name: string;
  providerType?: AIProviderType;
  baseUrl?: string | null;
  model?: string;
  timeout?: number;
  reasoningEffort?: string | null;
  requestHeaders?: {
    [k: string]: string;
  };
  requestParams?: {
    [k: string]: string;
  };
}
export interface AIProviderOut {
  name: string;
  providerType?: AIProviderType;
  baseUrl?: string | null;
  model?: string;
  timeout?: number;
  reasoningEffort?: string | null;
  requestHeaders?: {
    [k: string]: string;
  };
  requestParams?: {
    [k: string]: string;
  };
  id: string;
  chatgptAccount: string | null;
}
export interface AIProviderSave {
  name: string;
  providerType?: AIProviderType;
  baseUrl?: string | null;
  model?: string;
  timeout?: number;
  reasoningEffort?: string | null;
  requestHeaders?: {
    [k: string]: string;
  };
  requestParams?: {
    [k: string]: string;
  };
  settingsId: string;
}
export interface AIProviderSettingsCreate {
  groupId: string;
}
export interface AIProviderSettingsOut {
  defaultProviderId: string | null;
  audioProviderId: string | null;
  imageProviderId: string | null;
  taskSettings?: AITaskSettingOut[];
  providers: AIProviderSummary[];
  aiEnabled: boolean;
  audioProviderEnabled: boolean;
  imageProviderEnabled: boolean;
  imageReadingTasks: AITask[];
}
export interface AITaskSettingOut {
  task: AITask;
  providerId?: string | null;
  model?: string | null;
  reasoningEffort?: string | null;
  imageProviderId?: string | null;
  imageModel?: string | null;
  imageReasoningEffort?: string | null;
}
export interface AIProviderSummary {
  id: string;
  name: string;
  providerType?: AIProviderType;
  model?: string;
  reasoningEffort?: string | null;
}
export interface AIProviderSettingsUpdate {
  defaultProviderId: string | null;
  audioProviderId: string | null;
  imageProviderId: string | null;
  taskSettings?: AITaskSettingUpdate[] | null;
}
export interface AITaskSettingUpdate {
  task: AITask;
  providerId?: string | null;
  model?: string | null;
  reasoningEffort?: string | null;
  imageProviderId?: string | null;
  imageModel?: string | null;
  imageReasoningEffort?: string | null;
}
export interface AIProviderTestResult {
  success: boolean;
  message?: string | null;
  supportsImages?: boolean | null;
}
export interface AIProviderUpdate {
  name: string;
  providerType?: AIProviderType;
  baseUrl?: string | null;
  model?: string;
  timeout?: number;
  reasoningEffort?: string | null;
  requestHeaders?: {
    [k: string]: string;
  };
  requestParams?: {
    [k: string]: string;
  };
}
export interface AITaskSettingBase {
  task: AITask;
  providerId?: string | null;
  model?: string | null;
  reasoningEffort?: string | null;
  imageProviderId?: string | null;
  imageModel?: string | null;
  imageReasoningEffort?: string | null;
}
export interface ChatGPTLoginOut {
  id: string;
  state: ChatGPTLoginState;
  verificationUrl?: string | null;
  userCode?: string | null;
  account?: string | null;
  error?: string | null;
}
export interface CreateGroupPreferences {
  privateGroup?: boolean;
  showAnnouncements?: boolean;
  groupId: string;
}
export interface DataMigrationCreate {
  sourceType: SupportedMigrations;
}
export interface GroupAdminUpdate {
  id: string;
  name: string;
  preferences?: UpdateGroupPreferences | null;
  aiProviderSettings?: AIProviderSettingsUpdate | null;
}
export interface UpdateGroupPreferences {
  privateGroup?: boolean;
  showAnnouncements?: boolean;
}
export interface GroupDataExport {
  id: string;
  groupId: string;
  name: string;
  filename: string;
  path: string;
  size: string;
  expires: string;
}
export interface GroupStorage {
  usedStorageBytes: number;
  usedStorageStr: string;
  totalStorageBytes: number;
  totalStorageStr: string;
}
export interface ReadGroupPreferences {
  privateGroup?: boolean;
  showAnnouncements?: boolean;
  groupId: string;
  id: string;
}
export interface SeederConfig {
  locale: string;
}
