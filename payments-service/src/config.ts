export interface AppConfig {
  port: number;
  logLevel: string;
  env: 'development' | 'test' | 'production';
}

function parsePort(raw: string | undefined, fallback: number): number {
  if (!raw) return fallback;
  const n = Number(raw);
  if (!Number.isInteger(n) || n <= 0 || n > 65535) {
    throw new Error(`Invalid PORT value: ${raw}`);
  }
  return n;
}

function parseEnv(raw: string | undefined): AppConfig['env'] {
  if (raw === 'production' || raw === 'test') return raw;
  return 'development';
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  return {
    port: parsePort(env.PORT, 3000),
    logLevel: env.LOG_LEVEL ?? 'info',
    env: parseEnv(env.NODE_ENV),
  };
}
