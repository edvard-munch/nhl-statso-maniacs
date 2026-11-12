// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createSession, type Session } from '../../src/auth/session.js';
import { usePrivateRead } from '../../src/private/usePrivateRead.js';
let wrapper: VueWrapper | undefined;
let session: Session | undefined;
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  session?.dispose();
  session = undefined;
});
async function setup(read: () => Promise<{ secret: string }>) {
  session = createSession({
    fetch: async (input) =>
      new Response(
        JSON.stringify(
          String(input).endsWith('/csrf/')
            ? { csrf_token: 'fixture' }
            : { authenticated: true, user: { id: 1, username: 'First' } },
        ),
        { headers: { 'Content-Type': 'application/json' } },
      ),
  });
  await session.checkSession();
  let resource!: ReturnType<typeof usePrivateRead<{ secret: string }>>;
  wrapper = mount(
    defineComponent({
      setup() {
        resource = usePrivateRead(session!, { key: () => 'private', valid: () => true, read });
        return () => h('div');
      },
    }),
  );
  await flushPromises();
  return resource;
}
it('clears accepted private data and stops session watching on unmount', async () => {
  let reads = 0;
  const resource = await setup(async () => {
    reads += 1;
    return { secret: 'private saved value' };
  });
  expect(resource.data.value?.secret).toBe('private saved value');
  wrapper!.unmount();
  wrapper = undefined;
  expect(resource.data.value).toBeNull();
  await session!.checkSession();
  await flushPromises();
  expect(reads).toBe(1);
  expect(resource.data.value).toBeNull();
});
it('does not restore data from a response arriving after unmount even when transport ignores cancellation', async () => {
  let finish!: (value: { secret: string }) => void;
  const resource = await setup(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  wrapper!.unmount();
  wrapper = undefined;
  finish({ secret: 'late private value' });
  await flushPromises();
  expect(resource.data.value).toBeNull();
  expect(resource.phase.value).toBe('waiting');
});
