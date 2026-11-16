import { apiRequest } from "./apiClient";
import type { CandidateFile } from "./fileService";

export interface ProfileDate {
  value: string;
  precision: string;
}

export interface PersonalInfo {
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  city?: string | null;
  country?: {
    name: string;
    code: string;
  } | null;
  title?: string | null;
  summary?: string | null;
  /** Extracted field-record IDs, not file IDs. No candidate lookup endpoint exists. */
  field_ids?: Record<string, number>;
}

export interface Experience {
  company?: string | null;
  title?: string | null;
  location?: string | null;
  start_date?: ProfileDate | null;
  end_date?: ProfileDate | null;
  employment_status?: string | null;
  description?: string | null;
  field_ids?: number[];
}

export interface Education {
  institution?: string | null;
  degree?: string | null;
  field?: string | null;
  start_date?: ProfileDate | null;
  end_date?: ProfileDate | null;
  field_ids?: number[];
}

export interface Skill {
  name: string;
  level?: number | null;
  verified?: boolean;
  /** Stored backend skills use string(file_id); see provenanceService for validation. */
  sources?: string[];
  field_ids?: number[];
}

export interface Certification {
  name?: string | null;
  issuer?: string | null;
  issue_date?: ProfileDate | null;
  url?: string | null;
  field_ids?: number[];
}

export interface Project {
  name?: string | null;
  description?: string | null;
  url?: string | null;
  tech_stack?: string[];
  field_ids?: number[];
}

export interface ProfileLanguage {
  name: string;
  proficiency?: string | null;
  field_ids?: number[];
}

export interface ProfileLink {
  type: string;
  url: string;
  field_ids?: number[];
}

export interface UnifiedProfile {
  rule_version?: string;
  personal_info?: PersonalInfo | null;
  experience?: Experience[];
  education?: Education[];
  skills?: Skill[];
  certifications?: Certification[];
  projects?: Project[];
  languages?: ProfileLanguage[];
  links?: ProfileLink[];
}

export type ProfileFile = CandidateFile;

export interface CandidateProfileResponse {
  profile_id: number;
  candidate_name: string;
  candidate_email: string;
  updated_at: string | null;
  open_reviews: number;
  profile: UnifiedProfile | null;
  files: ProfileFile[];
}

export function getMyProfile(): Promise<CandidateProfileResponse | null> {
  return apiRequest("/profile/me", { allowNotFound: true, failureMessage: "We couldn't load your profile. Please try again." });
}