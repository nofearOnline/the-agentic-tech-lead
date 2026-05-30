import request from 'supertest';
import { createApp } from '../src/app';

describe('POST /charge', () => {
  const app = createApp();

  it('returns 201 with the created transaction for a valid request', async () => {
    const res = await request(app)
      .post('/charge')
      .send({
        amount: 2500,
        currency: 'USD',
        card: { number: '4242424242424242', expMonth: 12, expYear: 2030, cvc: '123' },
        customerId: 'cus_42',
      });

    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({
      status: 'succeeded',
      amount: 2500,
      currency: 'USD',
      cardLast4: '4242',
      customerId: 'cus_42',
    });
    expect(res.body.id).toMatch(/^txn_/u);
  });

  it('returns 400 with validation details for malformed payloads', async () => {
    const res = await request(app)
      .post('/charge')
      .send({ amount: -5, currency: 'XYZ', card: { number: 'abc', expMonth: 13, expYear: 1999, cvc: '1' } });

    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('validation_error');
    expect(res.body.error.details).toBeDefined();
  });

  it('returns 402 when the card is declined', async () => {
    const res = await request(app)
      .post('/charge')
      .send({
        amount: 100,
        currency: 'USD',
        card: { number: '4000000000000002', expMonth: 1, expYear: 2030, cvc: '123' },
      });

    expect(res.status).toBe(402);
    expect(res.body.error.code).toBe('card_declined');
  });

  it('does not echo full card numbers in the response', async () => {
    const res = await request(app)
      .post('/charge')
      .send({
        amount: 100,
        currency: 'USD',
        card: { number: '4242424242424242', expMonth: 12, expYear: 2030, cvc: '123' },
      });

    expect(JSON.stringify(res.body)).not.toContain('4242424242424242');
    expect(res.body.cardLast4).toBe('4242');
  });
});

describe('GET /transactions/:id', () => {
  const app = createApp();

  it('returns 404 for unknown transaction ids', async () => {
    const res = await request(app).get('/transactions/txn_does_not_exist');
    expect(res.status).toBe(404);
    expect(res.body.error.code).toBe('not_found');
  });

  it('round-trips a charge -> lookup', async () => {
    const created = await request(app)
      .post('/charge')
      .send({
        amount: 700,
        currency: 'EUR',
        card: { number: '4242424242424242', expMonth: 12, expYear: 2030, cvc: '123' },
      });
    expect(created.status).toBe(201);

    const fetched = await request(app).get(`/transactions/${created.body.id}`);
    expect(fetched.status).toBe(200);
    expect(fetched.body.id).toBe(created.body.id);
  });
});

describe('GET /health', () => {
  it('returns 200 ok', async () => {
    const res = await request(createApp()).get('/health');
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ status: 'ok' });
  });
});
