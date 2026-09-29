import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Modal } from './Modal';

describe('Modal', () => {
  it('is an accessible, labelled dialog that closes on Escape', async () => {
    const onClose = vi.fn();
    render(
      <Modal open title="Delete meeting?" description="This cannot be undone." onClose={onClose}>
        <button type="button">Confirm</button>
      </Modal>,
    );

    const dialog = screen.getByRole('dialog', { name: 'Delete meeting?' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleDescription('This cannot be undone.');
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();

    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('keeps focus inside the dialog when tabbing', async () => {
    render(
      <Modal open title="Test" onClose={() => {}}>
        <button type="button">Last</button>
      </Modal>,
    );
    await userEvent.tab();
    expect(screen.getByRole('button', { name: 'Last' })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus();
  });

  it('renders nothing when closed', () => {
    render(
      <Modal open={false} title="Hidden" onClose={() => {}}>
        content
      </Modal>,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
