import { Transaction } from '../domain/transaction';

export interface TransactionRepository {
  save(transaction: Transaction): Promise<Transaction>;
  findById(id: string): Promise<Transaction | null>;
  findAll(): Promise<Transaction[]>;
}

export class InMemoryTransactionRepository implements TransactionRepository {
  private readonly store = new Map<string, Transaction>();

  async save(transaction: Transaction): Promise<Transaction> {
    this.store.set(transaction.id, transaction);
    return transaction;
  }

  async findById(id: string): Promise<Transaction | null> {
    return this.store.get(id) ?? null;
  }

  async findAll(): Promise<Transaction[]> {
    return Array.from(this.store.values());
  }
}
