export type SectionStatus = 'red' | 'orange' | 'green' | 'neutral';

export interface AppConfig {
  app_name: string;
  default_machine_id: number;
  live_refresh_seconds: number;
  default_history_minutes: number;
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
