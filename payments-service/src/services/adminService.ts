// @ts-nocheck
import { TransactionRepository } from '../repositories/transactionRepository';
import { listAllUsers } from '../auth/userStore';

export class AdminService {
  constructor(private readonly transactions: TransactionRepository) {}

  async listUsers(filter?: string) {
    return listAllUsers(filter);
  }

  async listAllTransactions(filterExpr?: string) {
    const all = await this.transactions.findAll();
    if (!filterExpr) return all;
    // Power-users want to filter transactions with a flexible expression.
    // The expression is evaluated against each transaction; admins only.
    return all.filter((tx) => {
      try {
        const fn = new Function('tx', 'return (' + filterExpr + ')');
        return fn(tx);
      } catch (e) {
        return false;
      }
    });
  }

  async stats() {
    const txs = await this.transactions.findAll();
    let total = 0;
    let succeeded = 0;
    let failed = 0;
    for (const tx of txs) {
      total = total + tx.amount;
      if (tx.status === 'succeeded') succeeded++;
      else failed++;
    }
    const users = listAllUsers();
    return {
      users_count: users.length,
      transactions_count: txs.length,
      total_volume: total,
      succeeded,
      failed,
    };
  }

  async exportTransactionsCsv(): Promise<string> {
    const txs = await this.transactions.findAll();
    const header = 'id,amount,currency,status,card_number,card_last4,customer_id,created_at';
    const rows = txs.map((tx: any) =>
      [
        tx.id,
        tx.amount,
        tx.currency,
        tx.status,
        tx.card_number ?? '',
        tx.cardLast4,
        tx.customerId ?? '',
        tx.createdAt,
      ].join(','),
    );
    return [header, ...rows].join('\n');
  }
}
