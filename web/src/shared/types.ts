export type Trial = {
  model: string;
  quality: number;
  cost_per_case_eur: number;
  people_and_leakage_per_case_eur: number;
  p95_latency_s: number;
  passes: boolean;
  why: string;
};
export type Day = { week: number; day: number; low_confidence: number; psi: number; alarm: boolean };
export type RoutingDesign = {
  accuracy: number;
  accuracy_on_letter_answers: number;
  misroutes_per_week: number;
  llm_share: number;
  model_eur_per_month: number;
  people_hours_per_month: number;
  labels_from_people: number;
  weekly: number[];
};
export type InvoiceDesign = {
  settled_without_person: number;
  overpaid_per_1000_eur: number;
  underpaid_per_1000_eur: number;
  cost_per_invoice_eur: number;
  example: { id: string; invoice: string; billed: number; paid: number; notes: string[] } | null;
};
export type AssistDesign = { drafts_used: number; wrong_answers_per_1000: number; minutes_per_chat: number; cost_per_chat_eur: number };
export type Feasibility = { runtime: string; why: string; concurrency: number; crossover_cases_per_day: number; quota: { quota_share: number } };
export type Total = { model_eur_per_month: number; people_hours_per_month: number; overpaid_eur_per_month: number; all_in_eur_per_month: number };
export type Run = {
  world: string;
  volume: { weeks: number; live_from_week: number; emails: number; invoices: number; chats: number; letter_week: number };
  totals: Record<"large_everywhere" | "platform", Total>;
  selection: Record<string, { chosen: string; trials: Trial[] }>;
  feasibility: Record<string, Feasibility>;
  routing: {
    validation: { random_split: number; grouped_by_time_and_customer: number; production_before_letter: number };
    drift: { letter_week: number; detected_after_days: number | null; false_alarms_before_letter: number; alarm: { week: number; day: number; why: string[] } | null };
    designs: Record<string, RoutingDesign>;
    daily: Day[];
  };
  invoices: Record<string, InvoiceDesign>;
  assist: { retrieval: { tariff_words: number; paraphrased: number; paraphrased_after_rewrite: number }; floor: number; designs: Record<string, AssistDesign> };
};
export type Console = { dev: Run; heldout: Run | null; names: Record<string, Record<string, string>> };
