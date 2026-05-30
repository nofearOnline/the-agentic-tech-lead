import { createApp } from './app';
import { loadConfig } from './config';
import { logger } from './logger';

const config = loadConfig();
const app = createApp();

const server = app.listen(config.port, () => {
  logger.info({ port: config.port, env: config.env }, 'server_started');
});

function shutdown(signal: NodeJS.Signals): void {
  logger.info({ signal }, 'shutdown_requested');
  server.close((err) => {
    if (err) {
      logger.error({ err }, 'shutdown_failed');
      process.exit(1);
    }
    process.exit(0);
  });
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
