import { useState, type ChangeEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { ArrowLeft, FileText, Upload } from 'lucide-react';

import { ParticipantsInput } from './ParticipantsInput';
import { ReviewCommitments } from './ReviewCommitments';
import { ReviewSummary } from './ReviewSummary';
import { conversionNote, isCaptionFile, mergeSpeakers } from './transcriptFile';
import { meetingsApi } from '../../api/endpoints';
import { queryKeys, usePublicConfig, useRecentParticipants, useSamples } from '../../api/queries';
import { Alert } from '../../components/ui/Alert';
import { Button } from '../../components/ui/Button';
import { SelectField, TextAreaField, TextField } from '../../components/ui/Field';
import { errorMessage } from '../../lib/api';
import { pluralize, todayIso } from '../../lib/format';
import type { Meeting, Participant, ReviewResult, SampleTranscript } from '../../types/api';

const MEETING_TYPES = ['Standup', 'Sprint Planning', 'Architecture Review', 'Retrospective', 'Engineering Sync', 'Other'];
const MAX_FILE_BYTES = 1_000_000;
const TEXT_FILE = /\.(txt|md|vtt|srt)$/i;

type Step = 'details' | 'review' | 'done';

const STEPS: { id: Step; label: string }[] = [
  { id: 'details', label: 'Meeting & transcript' },
  { id: 'review', label: 'Review commitments' },
  { id: 'done', label: 'Tracked' },
];

interface Props {
  onCancel: () => void;
  onFinished: (meetingId: number) => void;
  onGoToCommitments: () => void;
}

export function NewMeetingWizard({ onCancel, onFinished, onGoToCommitments }: Props) {
  const queryClient = useQueryClient();
  const { data: samples = [] } = useSamples();
  const { data: recent = [] } = useRecentParticipants();
  const maxChars = usePublicConfig().data?.max_transcript_chars ?? 100_000;

  const [step, setStep] = useState<Step>('details');
  const [title, setTitle] = useState('');
  const [meetingType, setMeetingType] = useState('Standup');
  const [meetingDate, setMeetingDate] = useState(todayIso());
  const [meetingTime, setMeetingTime] = useState('');
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [transcript, setTranscript] = useState('');
  const [fileNote, setFileNote] = useState<string | null>(null);
  const [converting, setConverting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [result, setResult] = useState<ReviewResult | null>(null);

  const create = useMutation({
    mutationFn: meetingsApi.create,
    onSuccess: (created) => {
      setMeeting(created);
      setStep('review');
      queryClient.invalidateQueries({ queryKey: queryKeys.meetings });
      queryClient.invalidateQueries({ queryKey: queryKeys.participants });
    },
  });

  const suggestions = [...recent, ...samples.flatMap((s) => s.participants)].filter(
    (p, i, all) => all.findIndex((q) => q.name.toLowerCase() === p.name.toLowerCase()) === i,
  );

  const loadSample = (sample: SampleTranscript) => {
    setTitle(sample.title);
    setMeetingType(sample.meeting_type);
    setParticipants(sample.participants);
    setTranscript(sample.transcript);
    setFileNote(`Loaded sample transcript "${sample.title}".`);
    setFormError(null);
  };

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!TEXT_FILE.test(file.name)) {
      setFormError('Only plain-text transcripts (.txt, .md, .vtt, .srt) are supported. Export other formats as text first.');
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setFormError('That file is larger than 1 MB. Trim it or paste the relevant part.');
      return;
    }
    const text = await file.text();
    setFormError(null);
    if (!isCaptionFile(file.name, text)) {
      setTranscript(text);
      setFileNote(`Loaded ${file.name}.`);
      return;
    }
    // Teams / Zoom captions: drop timestamps and markup, keep "Name: text", and suggest the speakers as participants.
    setConverting(true);
    try {
      const result = await meetingsApi.convertTranscript(text);
      const merged = mergeSpeakers(participants, result.speakers);
      setTranscript(result.transcript);
      setParticipants(merged);
      setFileNote(conversionNote(file.name, result, merged.length - participants.length));
      if (result.too_long) setFormError(`The converted transcript is over ${maxChars.toLocaleString()} characters. Trim it before extracting.`);
    } catch (err) {
      setFileNote(null);
      setFormError(errorMessage(err, 'That caption file could not be read.'));
    } finally {
      setConverting(false);
    }
  };

  const submit = () => {
    if (!title.trim()) return setFormError('Give the meeting a name.');
    if (!transcript.trim()) return setFormError('Add a transcript by uploading a file or pasting text.');
    if (transcript.length > maxChars) return setFormError(`The transcript is over ${maxChars.toLocaleString()} characters.`);
    setFormError(null);
    create.mutate({
      title: title.trim(),
      meeting_type: meetingType,
      meeting_date: meetingDate || null,
      meeting_time: meetingTime || null,
      participants,
      transcript: transcript.trim(),
    });
  };

  const stepIndex = STEPS.findIndex((s) => s.id === step);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" onClick={onCancel} icon={<ArrowLeft size={15} aria-hidden="true" />}>
          Meetings
        </Button>
        <ol className="flex items-center gap-2 text-xs font-medium" aria-label="Progress">
          {STEPS.map((s, i) => (
            <li key={s.id} className="flex items-center gap-2">
              <span
                aria-current={i === stepIndex ? 'step' : undefined}
                className={clsx(
                  'rounded-full px-2.5 py-1',
                  i === stepIndex ? 'bg-brand text-white' : i < stepIndex ? 'bg-emerald-50 text-emerald-800' : 'bg-white text-muted',
                )}
              >
                {i + 1}. {s.label}
              </span>
            </li>
          ))}
        </ol>
      </div>

      {step === 'details' && (
        <div className="grid gap-6 lg:grid-cols-5">
          <section className="space-y-4 rounded-xl border border-line bg-white p-6 lg:col-span-2" aria-labelledby="meeting-details">
            <h2 id="meeting-details" className="text-base font-semibold text-ink">
              Meeting details
            </h2>
            <TextField label="Meeting name" value={title} maxLength={255} onChange={(e) => setTitle(e.target.value)} placeholder="Sprint 35 standup" />
            <SelectField label="Type" value={meetingType} onChange={(e) => setMeetingType(e.target.value)}>
              {MEETING_TYPES.map((type) => (
                <option key={type}>{type}</option>
              ))}
            </SelectField>
            <div className="grid grid-cols-2 gap-3">
              <TextField
                label="Date"
                type="date"
                value={meetingDate}
                onChange={(e) => setMeetingDate(e.target.value)}
                hint="Relative deadlines are resolved from this date."
              />
              <TextField label="Time (optional)" type="time" value={meetingTime} onChange={(e) => setMeetingTime(e.target.value)} />
            </div>
            <ParticipantsInput value={participants} onChange={setParticipants} suggestions={suggestions} />
          </section>

          <section className="space-y-4 rounded-xl border border-line bg-white p-6 lg:col-span-3" aria-labelledby="transcript-heading">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 id="transcript-heading" className="text-base font-semibold text-ink">
                Transcript
              </h2>
              <label className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-lg border border-line-strong bg-white px-3 text-xs font-semibold text-ink hover:bg-canvas focus-within:outline focus-within:outline-2 focus-within:outline-brand">
                <Upload size={13} aria-hidden="true" /> {converting ? 'Converting…' : 'Upload .txt, .vtt or .srt'}
                <input type="file" accept=".txt,.md,.vtt,.srt,text/plain,text/vtt" className="sr-only" disabled={converting} onChange={handleFile} />
              </label>
            </div>
            {samples.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="text-muted">Try a sample:</span>
                {samples.map((sample) => (
                  <button
                    key={sample.title}
                    type="button"
                    onClick={() => loadSample(sample)}
                    title={sample.description}
                    className="inline-flex items-center gap-1 rounded-full border border-line bg-canvas px-2.5 py-1 text-body hover:border-brand hover:text-brand"
                  >
                    <FileText size={11} aria-hidden="true" /> {sample.title}
                  </button>
                ))}
              </div>
            )}
            <TextAreaField
              label="Transcript text"
              rows={14}
              className="font-mono text-xs"
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              placeholder={'Maya: I will merge PR #101 in auth-service today.\nPriya: I\'ll fix issue #45 by tomorrow.'}
              hint={`${transcript.length.toLocaleString()} / ${maxChars.toLocaleString()} characters. Lines like "Name: text" work best; Teams and Zoom .vtt exports are converted automatically.`}
            />
            {fileNote && <p className="text-xs text-muted">{fileNote}</p>}
          </section>

          <div className="space-y-3 lg:col-span-5">
            {formError && <Alert tone="error">{formError}</Alert>}
            {create.isError && <Alert tone="error">{errorMessage(create.error, 'Analyzing the transcript failed.')}</Alert>}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={onCancel} disabled={create.isPending}>
                Cancel
              </Button>
              <Button onClick={submit} loading={create.isPending}>
                {create.isPending ? 'Extracting commitments…' : 'Extract commitments'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {step === 'review' && meeting && (
        <section aria-labelledby="review-heading" className="space-y-4">
          <div>
            <h2 id="review-heading" className="text-lg font-semibold text-ink">
              Review {pluralize(meeting.tasks.length, 'extracted commitment')}
            </h2>
            <p className="text-sm text-muted">
              {meeting.extraction_source === 'rules'
                ? 'Extracted with the rule-based parser (no AI key configured). Check owners and dates carefully.'
                : `Extracted with ${meeting.extraction_source === 'gemini' ? 'Gemini' : 'OpenAI'}.`}{' '}
              The meeting is saved; you can also finish this review later.
            </p>
          </div>
          <ReviewCommitments
            meeting={meeting}
            onCancel={() => onFinished(meeting.id)}
            onDone={(r) => {
              setResult(r);
              setStep('done');
            }}
          />
        </section>
      )}

      {step === 'done' && meeting && result && (
        <ReviewSummary result={result} onViewCommitments={onGoToCommitments} onDone={() => onFinished(meeting.id)} />
      )}
    </div>
  );
}
