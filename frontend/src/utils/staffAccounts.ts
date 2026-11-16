import { ApiError } from "../services/apiClient";
import type { CreateStaffRequest, StaffRole } from "../services/staffService";

export interface StaffFormValues { name: string; email: string; password: string; role: string }
export type StaffFormErrors = Partial<Record<keyof StaffFormValues, string>>;
export const staffRoleLabels: Record<StaffRole, string> = { reviewer: "Reviewer", administrator: "Administrator" };
export function staffErrorsAfterEdit(errors: StaffFormErrors, values: StaffFormValues, field: keyof StaffFormValues): StaffFormErrors {
  if (!errors[field]) return errors;
  const next = { ...errors };
  const message = validateStaffForm(values)[field];
  if (message) next[field] = message;
  else delete next[field];
  return next;
}
export function validateStaffForm(values: StaffFormValues): StaffFormErrors {
  const errors: StaffFormErrors = {};
  const length = [...values.name.trim()].length;
  if (length < 2 || length > 255) errors.name = "Enter a name of 2–255 characters.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) errors.email = "Enter a valid email address.";
  const passwordLength = [...values.password].length;
  if (passwordLength < 8 || passwordLength > 128) errors.password = "Enter a password of 8–128 characters.";
  if (values.role !== "reviewer" && values.role !== "administrator") errors.role = "Choose Reviewer or Administrator.";
  return errors;
}
export function prepareStaffRequest(values: StaffFormValues): CreateStaffRequest {
  if (Object.keys(validateStaffForm(values)).length) throw new ApiError("Check the name, email, password length and staff role.");
  return { name: values.name.trim(), email: values.email.trim().toLowerCase(), password: values.password, role: values.role as StaffRole };
}

