// Reads the workspace's gitignored src/.env (or .env); process.env always wins.
import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

export const workspaceRoot = resolve(import.meta.dirname, '../..');

export function parseEnvFile(path) {
  const values = {};
  if (!existsSync(path)) return values;
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const separator = trimmed.indexOf('=');
    if (separator < 1) continue;
    const key = trimmed.slice(0, separator).trim();
    let value = trimmed.slice(separator + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

export function loadWorkspaceEnv() {
  const envFile = [join(workspaceRoot, 'src', '.env'), join(workspaceRoot, '.env')].find(existsSync);
  return { envFile, env: { ...(envFile ? parseEnvFile(envFile) : {}), ...process.env } };
}
