import { describe, expect, it } from 'vitest';

import { conversionNote, isCaptionFile, mergeSpeakers } from './transcriptFile';

describe('transcript file helpers', () => {
  it('recognises caption files by extension or WEBVTT header', () => {
    expect(isCaptionFile('standup.vtt', 'anything')).toBe(true);
    expect(isCaptionFile('call.SRT', '1')).toBe(true);
    expect(isCaptionFile('notes.txt', '\uFEFFWEBVTT\n\n00:01.000 --> 00:02.000')).toBe(true);
    expect(isCaptionFile('notes.txt', 'Maya: I will merge PR #101 today.')).toBe(false);
  });

  it('adds only speakers who are not already participants, keeping roles', () => {
    const current = [{ name: 'Maya Chen', role: 'Engineering Lead' }];
    expect(mergeSpeakers(current, ['maya chen', 'Alex Moreno'])).toEqual([
      { name: 'Maya Chen', role: 'Engineering Lead' },
      { name: 'Alex Moreno' },
    ]);
  });

  it('describes the conversion', () => {
    const result = { transcript: '', format: 'vtt' as const, speakers: ['Maya Chen', 'Alex Moreno'], lines: 42, too_long: false };
    expect(conversionNote('Sprint review.vtt', result, 1)).toBe(
      'Converted Sprint review.vtt (caption file): 42 lines from 2 speakers. Added 1 to participants.',
    );
  });
});
