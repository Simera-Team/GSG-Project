import { getCandidateFileById, type CandidateFile } from "./fileService";
import { fileType } from "../utils/documents";

export interface SupportingDocument {
  fileId: number;
  name: string;
  documentType?: string;
}

// Verified against backend commit 6b84308: StoredDocumentReader and
// load_profile_field_records set source=str(file_id); ProfileBuilder._skills
// copies those source strings into SkillRecord.sources. field_ids are unrelated
// extracted-field record IDs and must never be used as document IDs.
export function skillSourceFileIds(sources?: readonly string[]): number[] {
  if (!Array.isArray(sources)) return [];
  const ids = sources.flatMap(source => {
    if (typeof source !== "string" || !/^[1-9]\d*$/.test(source)) return [];
    const id = Number(source);
    return Number.isSafeInteger(id) ? [id] : [];
  });
  return [...new Set(ids)];
}

function documentMetadata(file: CandidateFile, expectedId: number): SupportingDocument | null {
  if (file.file_id !== expectedId || typeof file.original_name !== "string" || !file.original_name.trim()) return null;
  return {
    fileId: file.file_id,
    name: file.original_name,
    documentType: typeof file.file_type === "string" && file.file_type.trim() ? fileType(file.file_type) : undefined,
  };
}

export async function getSkillSupportingDocuments(sources: readonly string[] | undefined, connectedFiles: readonly CandidateFile[]) {
  const ids = skillSourceFileIds(sources);
  const unknownReferences = Array.isArray(sources) ? new Set(sources.filter(source => !skillSourceFileIds([source]).length)).size : 0;
  const known = new Map(connectedFiles.map(file => [file.file_id, file]));
  const results = await Promise.allSettled(ids.map(async id => {
    const cached = known.get(id);
    const metadata = cached && documentMetadata(cached, id);
    if (metadata) return metadata;
    // profile/me.files is capped at 100 in the inspected implementation.
    // Resolve older references lazily through the candidate-owned metadata API.
    const file = await getCandidateFileById(id);
    return documentMetadata(file, id);
  }));
  const documents = results.flatMap(result => result.status === "fulfilled" && result.value ? [result.value] : []);
  return { documents, unavailableCount: unknownReferences + ids.length - documents.length };
}