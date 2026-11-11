import { afterEach, expect, it } from 'vitest';
import { cp, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const temporary: string[] = [];
afterEach(async () => {
  for (const directory of temporary.splice(0)) await rm(directory, { recursive: true, force: true });
});

async function fixture() {
  const directory = await mkdtemp(path.join(tmpdir(), 'nhl-client-contract-'));
  temporary.push(directory);
  const frontend = path.join(directory, 'frontend');
  const api = path.join(directory, 'api');
  const output = path.join(frontend, 'src/api/generated');
  await mkdir(api, { recursive: true });
  await mkdir(frontend, { recursive: true });
  await cp(path.join(ROOT, 'scripts'), path.join(frontend, 'scripts'), { recursive: true });
  await cp(path.join(ROOT, 'package.json'), path.join(frontend, 'package.json'));
  await cp(path.join(ROOT, '../api/openapi.json'), path.join(api, 'openapi.json'));
  await symlink(path.join(ROOT, 'node_modules'), path.join(frontend, 'node_modules'), 'junction');
  const run = (...args: string[]) => spawnSync(process.execPath, [path.join(frontend, 'scripts/generate-api.mjs'), ...args], {
    cwd: directory, encoding: 'utf8', env: { ...process.env, TZ: 'Pacific/Auckland' },
  });
  return { frontend, output, schema: path.join(api, 'openapi.json'), run };
}

it('generates every reviewed operation and keeps date, null and enum types', async () => {
  const schema = JSON.parse(await readFile(path.join(ROOT, '../api/openapi.json'), 'utf8'));
  const expected = Object.values(schema.paths as Record<string, Record<string, unknown>>)
    .flatMap(item => Object.keys(item).filter(method => ['get', 'post', 'put', 'patch', 'delete'].includes(method)));
  const sdk = await readFile(path.join(ROOT, 'src/api/generated/sdk.ts'), 'utf8');
  expect([...sdk.matchAll(/^export function /gm)]).toHaveLength(expected.length);
});

it('reproduces output from another checkout and check mode never rewrites it', async () => {
  const f = await fixture();
  const missing = f.run('--check');
  expect(missing.status, missing.stderr).toBe(1);
  await expect(readFile(path.join(f.output, 'sdk.ts'))).rejects.toThrow();
  const result = f.run();
  expect(result.status, result.stderr).toBe(0);
  for (const name of ['types.ts', 'sdk.ts']) {
    expect(await readFile(path.join(f.output, name))).toEqual(await readFile(path.join(ROOT, 'src/api/generated', name)));
  }
  const checked = f.run('--check');
  expect(checked.status, checked.stderr).toBe(0);
  const stale = `${await readFile(path.join(f.output, 'sdk.ts'), 'utf8')}\n// deliberately stale\n`;
  await writeFile(path.join(f.output, 'sdk.ts'), stale);
  const drift = f.run('--check');
  expect(drift.status).toBe(1);
  expect(drift.stderr, JSON.stringify(drift)).toContain('make api-client');
  expect(await readFile(path.join(f.output, 'sdk.ts'), 'utf8')).toBe(stale);
}, 15000);

it('detects extra generated files without deleting them during check', async () => {
  const f = await fixture();
  expect(f.run().status).toBe(0);
  await writeFile(path.join(f.output, 'extra.ts'), 'retained');
  expect(f.run('--check').status).toBe(1);
  expect(await readFile(path.join(f.output, 'extra.ts'), 'utf8')).toBe('retained');
});

it.each(['external reference', 'invalid schema'])('failed generation preserves the reviewed files: %s', async mode => {
  const f = await fixture();
  expect(f.run().status).toBe(0);
  const before = await readFile(path.join(f.output, 'sdk.ts'));
  const schema = JSON.parse(await readFile(f.schema, 'utf8'));
  if (mode === 'external reference') schema.components.schemas.Injected = { $ref: 'https://example.invalid/remote.json' };
  else schema.info.version = 42;
  await writeFile(f.schema, JSON.stringify(schema));
  const failed = f.run();
  expect(failed.status).not.toBe(0);
  if (mode === 'external reference') expect(failed.stderr).toContain('only local schema references');
  expect(await readFile(path.join(f.output, 'sdk.ts'))).toEqual(before);
});
