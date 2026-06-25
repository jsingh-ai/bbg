export type SectionStatus = 'red' | 'orange' | 'green' | 'neutral';

export interface AppConfig {
  app_name: string;
  default_machine_id: number;
  live_refresh_seconds: number;
  default_history_minutes: number;
  assistant_enabled: boolean;
}

export interface Machine {
  machine_id: number;
  machine_name: string;
  endpoint_url: string;
  main_image_path?: string | null;
  main_image_url?: string | null;
  is_active: number | boolean;
}

export interface Section {
  section_id: number;
  machine_id: number;
  section_key: string;
  display_label: string;
  section_photo_path?: string | null;
  section_photo_url?: string | null;
  is_visible: number | boolean;
  sort_order: number;
  box_x_pct?: number | null;
  box_y_pct?: number | null;
  box_w_pct?: number | null;
  box_h_pct?: number | null;
  has_box: boolean;
  tag_count: number;
  visible_tag_count: number;
  limit_count: number;
  open_alert_count: number;
  current_alert_count: number;
  status: SectionStatus;
}

export interface LiveValue {
  tag_id: number;
  opc_path: string;
  node_id: string;
  display_name?: string | null;
  browse_name?: string | null;
  data_type?: string | null;
  section_key: string;
  is_visible: number | boolean;
  show_in_history_default: number | boolean;
  sort_order: number;
  captured_at?: string | null;
  is_good?: number | boolean | null;
  value_kind?: number | null;
  value_num?: number | null;
  value_bool?: number | boolean | null;
  value_text?: string | null;
  error_text?: string | null;
  updated_at?: string | null;
  label: string;
  current_value: string;
  is_numeric: boolean;
}

export interface SectionLiveResponse {
  section: Section;
  values: LiveValue[];
}

export interface Recipe {
  recipe_id: number;
  machine_id: number;
  recipe_name: string;
  recipe_code?: string | null;
  description?: string | null;
  is_active: number | boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ActiveRecipe {
  machine_id: number;
  recipe_id?: number | null;
  selection_mode: 'manual' | 'automatic';
  selected_at?: string;
  updated_at?: string;
  recipe_name?: string | null;
  recipe_code?: string | null;
  description?: string | null;
  is_active?: number | boolean | null;
}

export interface AlertEvent {
  alert_id: number;
  machine_id: number;
  recipe_id?: number | null;
  tag_id: number;
  section_key: string;
  display_name?: string | null;
  alert_type: 'LOW' | 'HIGH' | 'LIMIT';
  min_value?: number | null;
  max_value?: number | null;
  trigger_value: number;
  current_value?: number | null;
  triggered_at: string;
  last_seen_at?: string | null;
  returned_to_range_at?: string | null;
  is_currently_out_of_range: number | boolean;
  is_acknowledged: number | boolean;
  acknowledged_at?: string | null;
  acknowledged_by?: string | null;
  acknowledge_note?: string | null;
}

export interface DashboardState {
  machine: Machine;
  active_recipe?: ActiveRecipe | null;
  sections: Section[];
  alerts: AlertEvent[];
}

export interface SummaryMetric {
  tag_id?: number;
  opc_path: string;
  label: string;
  current_value: string;
  value_num?: number | null;
  points: [string, number][];
}

export interface SummaryUptime {
  window_minutes: number;
  online_minutes: number;
  offline_minutes: number;
  down_minutes: number;
  uptime_pct: number;
}

export interface DashboardSummary {
  speed: SummaryMetric;
  production: {
    shift: { good: SummaryMetric; bad: SummaryMetric };
    job: { good: SummaryMetric; bad: SummaryMetric };
    total: { good: SummaryMetric; bad: SummaryMetric };
  };
  uptime: SummaryUptime;
}

export interface HistorySeries {
  tag_id: number;
  label: string;
  section_key?: string;
  points: [string, number][];
}

export interface HistoryResponse {
  series: HistorySeries[];
  start?: string;
  end?: string;
}

export interface AssistantCard {
  label: string;
  value: string | number;
  unit?: string;
}

export interface AssistantTable {
  title: string;
  columns: string[];
  rows: Array<Array<string | number | boolean | null>>;
}

export interface AssistantChatRequest {
  message: string;
  time_range?: string;
  conversation_id?: string;
}

export interface AssistantChatResponse {
  answer: string;
  intent: string;
  conversation_id?: string | null;
  cards: AssistantCard[];
  tables: AssistantTable[];
  raw: Record<string, unknown>;
}

export interface AssistantTagSuggestion {
  tag_id: number;
  label: string;
  opc_path: string;
}

export interface AssistantRequiredTagDiagnostic {
  configured_path: string;
  found: boolean;
  tag_id?: number;
  label?: string;
  last_sample_at?: string | null;
  last_value?: string | number | null;
  suggestions?: AssistantTagSuggestion[];
}

export interface AssistantDiagnosticsResponse {
  ok: boolean;
  assistant_enabled: boolean;
  openai_configured: boolean;
  timezone: string;
  config: {
    speed_tag_path: string;
    good_bags_tag_path: string;
    bad_bags_tag_path: string;
    total_bags_tag_path?: string;
    production_mode?: string;
    running_speed_threshold: number;
    min_stop_minutes: number;
    max_rows: number;
    excluded_section_keys?: string[];
    excluded_path_contains?: string[];
    excluded_tag_terms?: string[];
    excluded_state_terms?: string[];
    state_context_enabled?: boolean;
    dependent_speed_terms?: string[];
    speed_context_enabled?: boolean;
  };
  database: {
    connected: boolean;
    opc_tags_count: number | null;
    opc_tag_values_count_estimate: number | null;
    latest_history_timestamp: string | null;
    oldest_history_timestamp: string | null;
  };
  required_tags: {
    speed: AssistantRequiredTagDiagnostic;
    good_bags: AssistantRequiredTagDiagnostic;
    bad_bags: AssistantRequiredTagDiagnostic;
  };
  suggested_fixes: string[];
  version?: AssistantVersionResponse;
}

export interface AssistantVersionResponse {
  ok: boolean;
  service: string;
  raw_route_supported: boolean;
  started_at: string;
  process_id: number;
  git_commit?: string | null;
  git_branch?: string | null;
}

export interface AssistantProductionSampleStats {
  first?: { timestamp: string; value: number } | null;
  last?: { timestamp: string; value: number } | null;
  delta_sum: number;
  raw_delta: number;
  reset_count: number;
  sample_count: number;
}

export interface AssistantProductionTagInfo {
  configured_path: string;
  found: boolean;
  tag_id?: number;
  label?: string;
  opc_path?: string | null;
  suggestions?: AssistantTagSuggestion[];
}

export interface AssistantProductionDebugResponse {
  range: Record<string, unknown>;
  good_tag: AssistantProductionTagInfo;
  bad_tag: AssistantProductionTagInfo;
  total_tag?: AssistantProductionTagInfo;
  good_samples: AssistantProductionSampleStats;
  bad_samples: AssistantProductionSampleStats;
  total_samples?: AssistantProductionSampleStats;
  production_mode?: string;
  warnings: string[];
}

export interface AssistantProductionCandidate {
  tag_id: number;
  label: string;
  opc_path: string;
  section_key?: string | null;
  first_value?: number | null;
  last_value?: number | null;
  delta_sum: number;
  raw_delta: number;
  reset_count: number;
  sample_count: number;
}

export interface AssistantProductionCandidatesResponse {
  range: Record<string, unknown>;
  candidates: AssistantProductionCandidate[];
}

export interface SavedHistoryVariable {
  tag_id: number;
  label: string;
  section_key: string;
  current_value: string;
}

export interface RecipeLimitRow extends LiveValue {
  limit_id?: number | null;
  min_value?: number | null;
  max_value?: number | null;
  is_limit_enabled: number | boolean;
}

export interface RecipeLimitsResponse {
  recipe: Recipe;
  section_key: string;
  limits: RecipeLimitRow[];
}
