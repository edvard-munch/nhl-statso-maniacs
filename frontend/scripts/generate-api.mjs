import { readFile, readdir, mkdir, mkdtemp, rm, cp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createKubb } from '@kubb/core';
import { adapterOas } from '@kubb/adapter-oas';
import { parserTs } from '@kubb/parser-ts';
import { pluginTs } from '@kubb/plugin-ts';
import { pluginClient } from '@kubb/plugin-client';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const SCHEMA = path.resolve(ROOT, '../api/openapi.json');
const OUTPUT = path.resolve(ROOT, 'src/api/generated');
const CHECK_FLAG = '--check';
// OpenAPI's password hint is still a string; the transport preserves its value.
const PASSWORD_FORMAT_WARNING = 'KUBB_UNSUPPORTED_FORMAT';

function assertLocalReferences(value) {
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    if (key === '$ref' && (typeof child !== 'string' || !child.startsWith('#/'))) {
      throw new Error('Client generation accepts only local schema references.');
    }
    assertLocalReferences(child);
  }
}

async function files(directory, prefix = '') {
  const result = new Map();
  for (const entry of await readdir(directory, { withFileTypes: true }).catch((error) => {
    if (error.code === 'ENOENT') return [];
    throw error;
  })) {
    const relative = path.posix.join(prefix, entry.name);
    if (entry.isDirectory()) {
      for (const [name, content] of await files(path.join(directory, entry.name), relative))
        result.set(name, content);
    } else {
      result.set(relative, await readFile(path.join(directory, entry.name)));
    }
  }
  return result;
}

const check = process.argv.includes(CHECK_FLAG);
if (process.argv.slice(2).some((arg) => arg !== CHECK_FLAG))
  throw new Error('Use api:generate or api:check.');
const schema = JSON.parse(await readFile(SCHEMA, 'utf8'));
assertLocalReferences(schema);
const temporary = await mkdtemp(path.join(tmpdir(), 'nhl-api-client-'));
try {
  const engine = createKubb({
    root: ROOT,
    input: schema,
    adapter: adapterOas({ validate: true }),
    parsers: [parserTs({ extension: { '.ts': '.js' } })],
    output: { path: temporary, clean: false, defaultBanner: 'simple', format: false, lint: false },
    plugins: [
      pluginTs({ output: { path: 'types.ts' }, enum: { type: 'literal' } }),
      pluginClient({
        output: { path: 'sdk.ts' },
        importPath: '../http.js',
        throwOnErrorDefault: true,
      }),
    ],
  });
  const result = await engine.generate();
  engine.dispose();
  const problems = result.diagnostics.filter(
    (item) =>
      (item.kind ?? 'problem') === 'problem' &&
      item.severity !== 'info' &&
      !(item.code === PASSWORD_FORMAT_WARNING && item.message.includes('format "password"')),
  );
  if (!result.success || problems.length) {
    process.stderr.write(`${JSON.stringify(problems, null, 2)}\n`);
    throw new Error('API client generation failed or emitted diagnostics.');
  }
  const generated = await files(temporary);
  if (check) {
    const existing = await files(OUTPUT);
    if (
      existing.size !== generated.size ||
      [...generated].some(([name, content]) => !existing.get(name)?.equals(content))
    ) {
      process.stderr.write(
        'Generated API client is stale. Run make api-client and review the diff.\n',
      );
      process.exitCode = 1;
    } else console.log('Generated API client matches the reviewed schema.');
  } else {
    await mkdir(path.dirname(OUTPUT), { recursive: true });
    await rm(OUTPUT, { recursive: true, force: true });
    await cp(temporary, OUTPUT, { recursive: true });
    console.log(`Generated ${generated.size} API files from the reviewed schema.`);
  }
} finally {
  await rm(temporary, { recursive: true, force: true });
}
