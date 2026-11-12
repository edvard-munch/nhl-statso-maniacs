import { expect, it, vi } from 'vitest';
import { captureResetLink, createResetLinkSlot } from '../../src/auth/resetLink.js';

it('captures only the fragment and scrubs navigation before returning credentials', () => {
  const scrub = vi.fn();
  const result = captureResetLink(
    'https://nhl.test/recover-password/#uidb64=MQ&token=reset-secret',
    scrub,
  );
  expect(scrub).toHaveBeenCalledWith('/recover-password/');
  expect(result).toEqual({ uidb64: 'MQ', token: 'reset-secret' });
});

it.each([
  '#uidb64=MQ',
  '#token=secret',
  '#uidb64=MQ&token=',
  '#uidb64=MQ&token=one&token=two',
  '#uidb64=MQ&uidb64=Mg&token=secret',
  '#uidb64=MQ&token=secret&extra=value',
  `#uidb64=MQ&token=${'x'.repeat(129)}`,
])('rejects incomplete/ambiguous/oversized fragments without retaining them: %s', (hash) => {
  const scrub = vi.fn();
  expect(captureResetLink(`https://nhl.test/recover-password/${hash}`, scrub)).toBeNull();
  expect(scrub).toHaveBeenCalledWith('/recover-password/');
});

it('does not accept query tokens and also scrubs misplaced secrets before ordinary app navigation', () => {
  const scrub = vi.fn();
  expect(
    captureResetLink('https://nhl.test/recover-password/?uidb64=MQ&token=secret', scrub),
  ).toBeNull();
  expect(scrub).toHaveBeenCalledWith('/recover-password/');
  expect(captureResetLink('https://nhl.test/login#uidb64=MQ&token=secret', scrub)).toBeNull();
  expect(scrub).toHaveBeenLastCalledWith('/login');
});

it('leaves unrelated public anchors alone', () => {
  const scrub = vi.fn();
  expect(captureResetLink('https://nhl.test/games?date=2026-11-12#scores', scrub)).toBeNull();
  expect(scrub).not.toHaveBeenCalled();
});

it('offers the captured link once, with no persistence for reload/back navigation', () => {
  const slot = createResetLinkSlot({ uidb64: 'MQ', token: 'secret' });
  expect(slot.take()).toEqual({ uidb64: 'MQ', token: 'secret' });
  expect(slot.take()).toBeNull();
  const abandoned = createResetLinkSlot({ uidb64: 'Mg', token: 'other' });
  abandoned.clear();
  expect(abandoned.take()).toBeNull();
});
