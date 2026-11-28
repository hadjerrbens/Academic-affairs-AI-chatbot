import { Award, BookOpen, CalendarDays, ClipboardList, FileText, GraduationCap, Scale, ShieldCheck, Gauge, ScrollText } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type Topic = { icon: LucideIcon; title: string; prompt: string; login?: boolean };

/** Starter chips: one per feature that is wired to a tool. `login` = needs the student's own data. */
export const TOPICS: Topic[] = [
  { icon: GraduationCap, title: "Degree progress", prompt: "How far am I from graduating?", login: true },
  { icon: Gauge, title: "GPA & standing", prompt: "What is my academic standing and GPA?", login: true },
  { icon: BookOpen, title: "Degree requirements", prompt: "What are the degree requirements for BS_CS?" },
  { icon: CalendarDays, title: "Academic calendar", prompt: "What are the key dates this term?" },
  { icon: ClipboardList, title: "My exams", prompt: "When are my exams, and do any of them clash?", login: true },
  { icon: ScrollText, title: "Exam rules", prompt: "What can I bring to an exam?" },
  { icon: Scale, title: "Grading system", prompt: "How does the grading scale work?" },
  { icon: FileText, title: "Transcripts", prompt: "I need an official transcript.", login: true },
  { icon: Award, title: "Waivers & substitutions", prompt: "How do I request a course waiver?" },
  { icon: ShieldCheck, title: "Proctoring", prompt: "How does online proctoring work?" },
];

export const TOOL_LABELS: Record<string, string> = {
  get_major_requirements: "Looked up degree requirements",
  audit_degree_progress: "Audited your degree progress",
  get_academic_standing: "Checked your academic standing",
  get_academic_calendar: "Read the academic calendar",
  get_my_exam_schedule: "Loaded your exam schedule",
  get_exam_rules_summary: "Read the exam rules",
  explain_grading_system: "Looked up the grading scale",
  check_transcript_eligibility: "Checked transcript eligibility",
  propose_transcript_request: "Prepared a transcript request",
  explain_waiver_process: "Looked up the waiver process",
  check_waiver_eligibility: "Checked substitution eligibility",
  get_proctoring_info: "Looked up proctoring rules",
};
