import request from 'supertest';
import { createApp } from '../src/app';

describe('auth', () => {
  it('registers a new user and returns a token', async () => {
    const app = createApp();
    const res = await request(app)
      .post('/auth/register')
      .send({ email: 'alice@example.com', password: 'hunter2' });
    expect(res.status).toBe(201);
    expect(res.body.token).toBeDefined();
  });

  it('logs in an existing user', async () => {
    const app = createApp();
    await request(app)
      .post('/auth/register')
      .send({ email: 'bob@example.com', password: 'hunter2' });
    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'bob@example.com', password: 'hunter2' });
    expect(res.status).toBe(200);
    expect(res.body.token).toBeDefined();
  });
});
