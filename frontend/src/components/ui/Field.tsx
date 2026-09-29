import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react';
import clsx from 'clsx';

export const inputClass =
  'w-full rounded-lg border border-line-strong bg-white px-3 text-sm text-ink placeholder:text-subtle ' +
  'focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 disabled:bg-canvas disabled:text-muted';

interface FieldShellProps {
  label: string;
  hint?: ReactNode;
  error?: string;
  children: (id: string, describedBy?: string) => ReactNode;
}

function FieldShell({ label, hint, error, children }: FieldShellProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const describedBy = error || hint ? hintId : undefined;
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-ink">
        {label}
      </label>
      {children(id, describedBy)}
      {(error || hint) && (
        <p id={hintId} className={clsx('text-xs', error ? 'text-rose-700' : 'text-muted')}>
          {error ?? hint}
        </p>
      )}
    </div>
  );
}

type TextFieldProps = InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: ReactNode; error?: string };

export function TextField({ label, hint, error, className, ...rest }: TextFieldProps) {
  return (
    <FieldShell label={label} hint={hint} error={error}>
      {(id, describedBy) => (
        <input
          id={id}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className={clsx(inputClass, 'h-10', className)}
          {...rest}
        />
      )}
    </FieldShell>
  );
}

type SelectFieldProps = SelectHTMLAttributes<HTMLSelectElement> & { label: string; hint?: ReactNode; children: ReactNode };

export function SelectField({ label, hint, className, children, ...rest }: SelectFieldProps) {
  return (
    <FieldShell label={label} hint={hint}>
      {(id, describedBy) => (
        <select id={id} aria-describedby={describedBy} className={clsx(inputClass, 'h-10', className)} {...rest}>
          {children}
        </select>
      )}
    </FieldShell>
  );
}

type TextAreaFieldProps = TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: ReactNode };

export function TextAreaField({ label, hint, className, ...rest }: TextAreaFieldProps) {
  return (
    <FieldShell label={label} hint={hint}>
      {(id, describedBy) => (
        <textarea id={id} aria-describedby={describedBy} className={clsx(inputClass, 'py-2', className)} {...rest} />
      )}
    </FieldShell>
  );
}
