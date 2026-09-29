import { CalendarDays, ChevronRight } from 'lucide-react';

import { formatDate, pluralize } from '../../lib/format';
import type { MeetingListItem } from '../../types/api';

export function MeetingList({ meetings, onOpen }: { meetings: MeetingListItem[]; onOpen: (id: number) => void }) {
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-white">
      {meetings.map((meeting) => (
        <li key={meeting.id}>
          <button
            type="button"
            onClick={() => onOpen(meeting.id)}
            className="group flex w-full items-center justify-between gap-4 px-5 py-4 text-left hover:bg-canvas focus-visible:bg-canvas focus-visible:outline-none"
          >
            <div className="min-w-0 space-y-1">
              <div className="truncate font-semibold text-ink group-hover:text-brand">{meeting.title}</div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                <span className="inline-flex items-center gap-1">
                  <CalendarDays size={12} aria-hidden="true" />
                  {formatDate(meeting.meeting_date)}
                  {meeting.meeting_time && ` · ${meeting.meeting_time}`}
                </span>
                {meeting.meeting_type && <span>{meeting.meeting_type}</span>}
                {meeting.participants.length > 0 && <span>{pluralize(meeting.participants.length, 'participant')}</span>}
              </div>
              <div className="flex flex-wrap gap-x-3 text-xs">
                <span className="font-medium text-ink">{pluralize(meeting.task_count, 'commitment')}</span>
                {meeting.pending_count > 0 && <span className="font-medium text-amber-700">{meeting.pending_count} need review</span>}
                {meeting.approved_count > 0 && <span className="text-body">{meeting.approved_count} tracked</span>}
                {meeting.verified_count > 0 && <span className="text-emerald-700">{meeting.verified_count} verified done</span>}
              </div>
            </div>
            <ChevronRight size={16} className="shrink-0 text-subtle group-hover:text-brand" aria-hidden="true" />
          </button>
        </li>
      ))}
    </ul>
  );
}
