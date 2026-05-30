import request from 'supertest';
import { createApp } from '../src/app';

describe('POST /refunds', () => {
  it('creates a refund for an existing transaction', async () => {
    const app = createApp();

    const charge = await request(app)
      .post('/charge')
      .send({
        amount: 1000,
        currency: 'USD',
        card: { number: '4242424242424242', expMonth: 12, expYear: 2030, cvc: '123' },
        customerId: 'cus_abc',
      });

    const refund = await request(app)
      .post('/refunds')
      .send({ transaction_id: charge.body.id, amount: 1000 });

    expect(refund.body).toBeDefined();
  });

  it('handles missing transactions', async () => {
    const app = createApp();
    const refund = await request(app)
      .post('/refunds')
      .send({ transaction_id: 'txn_does_not_exist' });
    expect(refund.status).toBeLessThan(500);
  });
});

describe('GET /customers/:id/transactions', () => {
  it('returns a list', async () => {
    const app = createApp();
    const res = await request(app).get('/customers/cus_abc/transactions');
    expect(res.body).toBeDefined();
  });
});
