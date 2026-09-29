import { useId, useState, type KeyboardEvent } from 'react';
import { Plus, X } from 'lucide-react';

import { inputClass } from '../../components/ui/Field';
import { Button } from '../../components/ui/Button';
import type { Participant } from '../../types/api';

interface Props {
  value: Participant[];
  onChange: (next: Participant[]) => void;
  suggestions: Participant[];
}

export function ParticipantsInput({ value, onChange, suggestions }: Props) {
  const inputId = useId();
  const listId = useId();
  const [draft, setDraft] = useState('');

  const has = (name: string) => value.some((p) => p.name.toLowerCase() === name.toLowerCase());

  const add = (name: string) => {
    const clean = name.trim().replace(/\s+/g, ' ');
    if (!clean || has(clean) || clean.length > 120) return;
    const known = suggestions.find((s) => s.name.toLowerCase() === clean.toLowerCase());
    onChange([...value, known ?? { name: clean }]);
    setDraft('');
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault();
      add(draft);
    } else if (event.key === 'Backspace' && !draft && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  const unused = suggestions.filter((s) => !has(s.name));

  return (
    <div className="space-y-2">
      <label htmlFor={inputId} className="block text-sm font-medium text-ink">
        Participants
      </label>
      <p className="text-xs text-muted">Used to match speaker names in the transcript to full names. Press Enter to add.</p>
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Selected participants">
          {value.map((person) => (
            <li key={person.name} className="inline-flex items-center gap-1.5 rounded-full border border-line bg-canvas py-1 pl-3 pr-1.5 text-sm text-ink">
              {person.name}
              {person.role && <span className="text-xs text-muted">· {person.role}</span>}
              <button
                type="button"
                onClick={() => onChange(value.filter((p) => p.name !== person.name))}
                aria-label={`Remove ${person.name}`}
                className="rounded-full p-0.5 text-subtle hover:bg-line hover:text-ink"
              >
                <X size={12} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <input
          id={inputId}
          list={listId}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Type a name"
          className={`${inputClass} h-10`}
          maxLength={120}
        />
        <datalist id={listId}>
          {unused.map((s) => (
            <option key={s.name} value={s.name} />
          ))}
        </datalist>
        <Button variant="secondary" onClick={() => add(draft)} disabled={!draft.trim()} icon={<Plus size={14} aria-hidden="true" />}>
          Add
        </Button>
      </div>
      {unused.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-muted">From earlier meetings:</span>
          {unused.slice(0, 8).map((s) => (
            <button
              key={s.name}
              type="button"
              onClick={() => add(s.name)}
              className="rounded-full border border-line bg-white px-2 py-0.5 text-body hover:border-brand hover:text-brand"
            >
              + {s.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
