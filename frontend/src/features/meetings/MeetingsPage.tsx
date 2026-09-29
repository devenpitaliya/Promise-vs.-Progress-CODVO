import { useState } from 'react';
import { CalendarDays, Plus } from 'lucide-react';

import { MeetingDetail } from './MeetingDetail';
import { MeetingList } from './MeetingList';
import { NewMeetingWizard } from './NewMeetingWizard';
import { useMeetings } from '../../api/queries';
import { Button } from '../../components/ui/Button';
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../../components/ui/States';

type View = { kind: 'list' } | { kind: 'new' } | { kind: 'detail'; id: number };

interface Props {
  onOpenTask: (id: number) => void;
  onGoToCommitments: () => void;
}

export function MeetingsPage({ onOpenTask, onGoToCommitments }: Props) {
  const [view, setView] = useState<View>({ kind: 'list' });
  const { data: meetings, isLoading, error, refetch } = useMeetings();

  if (view.kind === 'new') {
    return (
      <NewMeetingWizard
        onCancel={() => setView({ kind: 'list' })}
        onFinished={(id) => setView({ kind: 'detail', id })}
        onGoToCommitments={onGoToCommitments}
      />
    );
  }

  if (view.kind === 'detail') {
    return (
      <MeetingDetail
        meetingId={view.id}
        onBack={() => setView({ kind: 'list' })}
        onOpenTask={onOpenTask}
        onGoToCommitments={onGoToCommitments}
      />
    );
  }

  const newMeetingButton = (
    <Button onClick={() => setView({ kind: 'new' })} icon={<Plus size={15} aria-hidden="true" />}>
      New meeting
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Meetings"
        description="Upload a transcript, review the commitments it contains, and track them against GitHub."
        actions={newMeetingButton}
      />
      {isLoading ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !meetings || meetings.length === 0 ? (
        <EmptyState icon={<CalendarDays size={20} aria-hidden="true" />} title="No meetings yet" action={newMeetingButton}>
          Start with a standup or planning transcript. Sample transcripts are available in the upload step.
        </EmptyState>
      ) : (
        <MeetingList meetings={meetings} onOpen={(id) => setView({ kind: 'detail', id })} />
      )}
    </>
  );
}
