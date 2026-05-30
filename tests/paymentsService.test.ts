import { PaymentsService, ChargeInput } from '../src/services/paymentsService';
import { InMemoryTransactionRepository } from '../src/repositories/transactionRepository';
import { FakeGateway } from '../src/gateway/fakeGateway';
import { AppError } from '../src/errors';

function buildInput(overrides: Partial<ChargeInput> = {}): ChargeInput {
  return {
    amount: 1999,
    currency: 'USD',
    card: {
      number: '4242424242424242',
      expMonth: 12,
      expYear: 2030,
      cvc: '123',
    },
    customerId: 'cus_123',
    ...overrides,
  };
}

describe('PaymentsService', () => {
  it('charges a card and persists a succeeded transaction', async () => {
    const repo = new InMemoryTransactionRepository();
    const service = new PaymentsService(new FakeGateway(), repo);

    const tx = await service.charge(buildInput());

    expect(tx.status).toBe('succeeded');
    expect(tx.amount).toBe(1999);
    expect(tx.currency).toBe('USD');
    expect(tx.cardLast4).toBe('4242');
    expect(tx.gatewayReference).toMatch(/^auth_/u);
    expect(tx.id).toMatch(/^txn_/u);

    const persisted = await repo.findById(tx.id);
    expect(persisted).toEqual(tx);
  });

  it('throws card_declined for cards ending in 0002 and persists the failed transaction', async () => {
    const repo = new InMemoryTransactionRepository();
    const service = new PaymentsService(new FakeGateway(), repo);

    const declined = buildInput({
      card: { number: '4000000000000002', expMonth: 1, expYear: 2030, cvc: '123' },
    });

    await expect(service.charge(declined)).rejects.toMatchObject({
      code: 'card_declined',
      statusCode: 402,
    });

    const all = await Promise.all(
      [...((repo as unknown as { store: Map<string, unknown> }).store).values()],
    );
    expect(all).toHaveLength(1);
  });

  it('rejects non-integer or non-positive amounts before contacting the gateway', async () => {
    const repo = new InMemoryTransactionRepository();
    const service = new PaymentsService(new FakeGateway(), repo);

    await expect(service.charge(buildInput({ amount: 0 }))).rejects.toThrow();
    await expect(service.charge(buildInput({ amount: -1 }))).rejects.toThrow();
    await expect(service.charge(buildInput({ amount: 1.5 }))).rejects.toThrow();
  });

  it('throws AppError(not_found) when looking up a missing transaction', async () => {
    const service = new PaymentsService(new FakeGateway(), new InMemoryTransactionRepository());
    await expect(service.getTransaction('nope')).rejects.toBeInstanceOf(AppError);
  });
});
