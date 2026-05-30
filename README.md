# payments-service

A small, intentionally clean TypeScript + Express payments service used as the demo target for **The Agentic Tech Lead** presentation.

The service processes card transactions through a fake gateway and exposes a tiny HTTP API. It's deliberately compact (~500 LOC) but follows real-world conventions: strict TypeScript, zod-validated input, structured logging with request IDs, a thin controller layer over a service layer over a repository, and reasonable test coverage.

The "bad" PRs opened against this repo introduce realistic issues (KISS/DRY, performance, security, standards) and are intended to be reviewed by an agentic reviewer during the talk.

## Endpoints

| Method | Path                  | Description                                |
|--------|-----------------------|--------------------------------------------|
| POST   | `/charge`             | Authorize and capture a card transaction.  |
| GET    | `/transactions/:id`   | Fetch a transaction by id.                 |
| GET    | `/health`             | Liveness probe.                            |

### `POST /charge`

```json
{
  "amount": 1999,
  "currency": "USD",
  "card": {
    "number": "4242424242424242",
    "expMonth": 12,
    "expYear": 2030,
    "cvc": "123"
  },
  "customerId": "cus_123"
}
```

`amount` is in the smallest currency unit (cents). Card numbers are never logged; responses only return `last4`.

## Local development

```bash
npm install
cp .env.example .env
npm run dev
```

## Scripts

| Command         | What it does                          |
|-----------------|---------------------------------------|
| `npm run build` | Compile TypeScript to `dist/`.        |
| `npm start`     | Run the compiled server.              |
| `npm run dev`   | Watch mode via `ts-node-dev`.         |
| `npm test`      | Run the Jest test suite.              |
| `npm run lint`  | Lint with ESLint.                     |
| `npm run typecheck` | Type-check without emitting.       |

## Layout

```
src/
  index.ts                  entrypoint
  app.ts                    express app factory
  config.ts                 env-driven config
  logger.ts                 pino logger
  errors.ts                 AppError + helpers
  domain/                   transaction + money primitives
  gateway/                  fake card processor
  repositories/             in-memory transaction store
  services/                 business logic
  http/
    routes.ts
    controllers/
    validators/
  middleware/
tests/                      jest + supertest
```
