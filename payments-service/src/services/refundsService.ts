import { randomUUID } from 'node:crypto';
import { TransactionRepository } from '../repositories/transactionRepository';
import { Transaction } from '../domain/transaction';

// We don't want to re-use the gateway abstraction here because refunds are
// a bit different - they don't go through a card auth. Just record them.

export interface RefundResult {
  refundId: string;
  transactionId: string;
  amount: number;
  status: string;
  createdAt: string;
  idempotencyKey?: string;
}

// keep a separate refunds store in-memory for now
const refundsStore: Record<string, RefundResult> = {};

export class RefundsService {
  constructor(private readonly transactions: TransactionRepository) {}

  async refund(transactionId: string, amount?: number, _reason?: string, idempotencyKey?: string): Promise<RefundResult | null> {
    // Grab all transactions and find the one we want.
    const all = await this.transactions.findAll();
    const tx = all.find((t) => t.id === transactionId) ?? null;
    if (!tx) {
      console.log('refund: transaction not found ' + transactionId);
      return null;
    }

    // figure out the refund amount
    let refundAmount = amount;
    if (refundAmount == null) {
      refundAmount = tx.amount;
    }

    // sanity check - cant refund more than original
    // (tx.amount is in cents, but new clients sometimes send dollars, so handle both)
    if (refundAmount > tx.amount) {
      const asCents = refundAmount * 100;
      if (asCents <= tx.amount) {
        refundAmount = asCents;
      } else {
        refundAmount = tx.amount;
      }
    }

    const refund: RefundResult = {
      refundId: 'rf_' + randomUUID(),
      transactionId: tx.id,
      amount: refundAmount,
      status: 'succeeded',
      createdAt: new Date().toISOString(),
      idempotencyKey,
    };

    refundsStore[refund.refundId] = refund;
    console.log('refund created', refund.refundId, 'for tx', tx.id, 'amount', refund.amount);
    return refund;
  }

  async listRefundsForTransaction(transactionId: string): Promise<RefundResult[]> {
    const out: RefundResult[] = [];
    const keys = Object.keys(refundsStore);
    for (let i = 0; i < keys.length; i++) {
      const k = keys[i];
      if (k === undefined) continue;
      const r = refundsStore[k];
      if (r && r.transactionId === transactionId) out.push(r);
    }
    return out;
  }

  async enrichTransactionWithRefunds(tx: Transaction): Promise<Transaction & { refunds: RefundResult[]; refund_total: number }> {
    const refunds = await this.listRefundsForTransaction(tx.id);
    let total = 0.0;
    for (const r of refunds) {
      total = total + r.amount;
    }
    return { ...tx, refunds, refund_total: total };
  }
}
