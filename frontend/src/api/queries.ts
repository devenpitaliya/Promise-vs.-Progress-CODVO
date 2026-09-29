import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { briefingsApi, commitmentsApi, configApi, integrationsApi, meetingsApi, reconciliationApi, settingsApi } from './endpoints';
import type { TaskUpdate } from '../types/api';

export const queryKeys = {
  config: ['config'] as const,
  meetings: ['meetings'] as const,
  meeting: (id: number) => ['meetings', id] as const,
  samples: ['samples'] as const,
  participants: ['participants'] as const,
  commitments: ['commitments'] as const,
  report: (meetingId?: number) => ['report', meetingId ?? 'all'] as const,
  schedules: ['schedules'] as const,
  emails: ['emails'] as const,
  aiSettings: ['ai-settings'] as const,
  system: ['system'] as const,
  integrations: ['integrations'] as const,
};

/** Server-side limits and flags from the project `.env` (MAX_TRANSCRIPT_CHARS, DEMO_MODE, ...). */
export const usePublicConfig = () => useQuery({ queryKey: queryKeys.config, queryFn: configApi.get, staleTime: Infinity });
export const useMeetings = () => useQuery({ queryKey: queryKeys.meetings, queryFn: meetingsApi.list });
export const useMeeting = (id: number | null) =>
  useQuery({ queryKey: queryKeys.meeting(id ?? 0), queryFn: () => meetingsApi.get(id as number), enabled: id !== null });
export const useSamples = () => useQuery({ queryKey: queryKeys.samples, queryFn: meetingsApi.samples, staleTime: Infinity });
export const useRecentParticipants = () => useQuery({ queryKey: queryKeys.participants, queryFn: meetingsApi.participants });
export const useCommitments = () => useQuery({ queryKey: queryKeys.commitments, queryFn: () => commitmentsApi.list() });
export const useReport = (meetingId?: number) =>
  useQuery({ queryKey: queryKeys.report(meetingId), queryFn: () => reconciliationApi.report(meetingId) });
export const useSchedules = () => useQuery({ queryKey: queryKeys.schedules, queryFn: briefingsApi.schedules });
export const useEmails = () => useQuery({ queryKey: queryKeys.emails, queryFn: briefingsApi.emails });
export const useAiSettings = () => useQuery({ queryKey: queryKeys.aiSettings, queryFn: settingsApi.ai });
export const useIntegrations = () => useQuery({ queryKey: queryKeys.integrations, queryFn: integrationsApi.list });
export const useSystemStatus = () => useQuery({ queryKey: queryKeys.system, queryFn: settingsApi.system, staleTime: 60_000 });

/** Invalidate everything derived from commitments after any change to them. */
export function useInvalidateTracking() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: queryKeys.meetings }),
      client.invalidateQueries({ queryKey: queryKeys.commitments }),
      client.invalidateQueries({ queryKey: ['report'] }),
    ]);
}

export function useUpdateCommitment() {
  const invalidate = useInvalidateTracking();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: TaskUpdate }) => commitmentsApi.update(id, payload),
    onSuccess: invalidate,
  });
}

export function useRunReconciliation() {
  const client = useQueryClient();
  const invalidate = useInvalidateTracking();
  return useMutation({
    mutationFn: (meetingId?: number) => reconciliationApi.run(meetingId),
    onSuccess: (report) => {
      client.setQueryData(queryKeys.report(report.meeting_id ?? undefined), report);
      return invalidate();
    },
  });
}
