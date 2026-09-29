import type { ConvertedTranscript, Participant } from '../../types/api';

/** Teams / Zoom caption exports and subtitle files, converted to "Name: text" on the server. */
export function isCaptionFile(fileName: string, text: string): boolean {
  return /\.(vtt|srt)$/i.test(fileName) || /^\uFEFF?\s*WEBVTT/.test(text);
}

/** Add detected speakers that are not already in the participant list (case-insensitive), keeping existing roles. */
export function mergeSpeakers(current: Participant[], speakers: string[]): Participant[] {
  const known = new Set(current.map((p) => p.name.trim().toLowerCase()));
  const added = speakers.filter((name) => !known.has(name.trim().toLowerCase())).map((name) => ({ name }));
  return [...current, ...added];
}

export function conversionNote(fileName: string, result: ConvertedTranscript, added: number): string {
  const kind = result.format === 'srt' ? 'subtitle file' : 'caption file';
  const people = result.speakers.length === 1 ? '1 speaker' : `${result.speakers.length} speakers`;
  const participants = added > 0 ? ` Added ${added} to participants.` : '';
  return `Converted ${fileName} (${kind}): ${result.lines} lines from ${people}.${participants}`;
}
