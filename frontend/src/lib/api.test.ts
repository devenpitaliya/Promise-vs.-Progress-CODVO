import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios';
import { describe, expect, it, vi } from 'vitest';

import { api, errorMessage, SESSION_EXPIRED_EVENT, tokenStore } from './api';

function axiosError(status: number, data: unknown, url = '/meetings/'): AxiosError {
  const config = { url, headers: new AxiosHeaders() } as InternalAxiosRequestConfig;
  return new AxiosError('failed', 'ERR', config, undefined, { status, data, statusText: '', headers: {}, config });
}

describe('errorMessage', () => {
  it('uses string details from the API', () => {
    expect(errorMessage(axiosError(409, { detail: 'Already reviewed.' }))).toBe('Already reviewed.');
  });

  it('flattens FastAPI validation errors', () => {
    const error = axiosError(422, { detail: [{ loc: ['body', 'recipient_email'], msg: 'value is not a valid email address' }] });
    expect(errorMessage(error)).toBe('recipient_email: value is not a valid email address');
  });

  it('explains network failures and server errors', () => {
    const network = new AxiosError('Network Error', 'ERR_NETWORK', { url: '/x', headers: new AxiosHeaders() } as InternalAxiosRequestConfig);
    expect(errorMessage(network)).toMatch(/reach the server/);
    expect(errorMessage(axiosError(500, {}))).toMatch(/server hit an error/);
  });
});

describe('session expiry', () => {
  it('clears the token and notifies the app on a 401 from a data endpoint', async () => {
    tokenStore.set('expired');
    const listener = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, listener);

    const rejected = api.interceptors.response as unknown as { handlers: { rejected: (e: unknown) => Promise<unknown> }[] };
    await expect(rejected.handlers[0].rejected(axiosError(401, { detail: 'Invalid or expired session' }))).rejects.toBeTruthy();

    expect(tokenStore.get()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
  });

  it('does not treat a failed sign-in as an expired session', async () => {
    tokenStore.set('still-valid');
    const rejected = api.interceptors.response as unknown as { handlers: { rejected: (e: unknown) => Promise<unknown> }[] };
    await expect(rejected.handlers[0].rejected(axiosError(401, { detail: 'Incorrect email or password.' }, '/auth/login'))).rejects.toBeTruthy();
    expect(tokenStore.get()).toBe('still-valid');
  });
});
