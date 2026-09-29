import { describe, expect, it } from 'vitest';

import { formatDate, initials, pluralize } from './format';

describe('format helpers', () => {
  it('formats ISO dates without shifting the day across timezones', () => {
    expect(formatDate('2026-09-30')).toContain('30');
    expect(formatDate(null)).toBe('Not set');
  });

  it('builds initials from names', () => {
    expect(initials('Maya Chen')).toBe('MC');
    expect(initials('priya')).toBe('P');
    expect(initials('')).toBe('?');
  });

  it('pluralizes counts', () => {
    expect(pluralize(1, 'commitment')).toBe('1 commitment');
    expect(pluralize(3, 'commitment')).toBe('3 commitments');
  });
});
