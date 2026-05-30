import { InMemoryTransactionRepository } from '../src/repositories/transactionRepository';
import { Transaction } from '../src/domain/transaction';

function makeTransaction(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: 'txn_test',
    amount: 100,
    currency: 'USD',
    status: 'succeeded',
    cardLast4: '4242',
    gatewayReference: 'auth_abc',
    createdAt: new Date('2025-01-01T00:00:00Z').toISOString(),
    ...overrides,
  };
}

describe('InMemoryTransactionRepository', () => {
  it('saves and retrieves a transaction by id', async () => {
    const repo = new InMemoryTransactionRepository();
    const tx = makeTransaction();
    await repo.save(tx);

    const found = await repo.findById(tx.id);
    expect(found).toEqual(tx);
  });

  it('returns null for unknown ids', async () => {
    const repo = new InMemoryTransactionRepository();
    expect(await repo.findById('nope')).toBeNull();
  });

  it('overwrites a transaction stored under the same id', async () => {
    const repo = new InMemoryTransactionRepository();
    await repo.save(makeTransaction({ status: 'failed' }));
    await repo.save(makeTransaction({ status: 'succeeded' }));

    const found = await repo.findById('txn_test');
    expect(found?.status).toBe('succeeded');
  });
});
