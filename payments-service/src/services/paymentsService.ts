import { randomUUID } from 'node:crypto';
import { Currency, assertPositiveAmount } from '../domain/money';
import { Transaction } from '../domain/transaction';
import { PaymentGateway } from '../gateway/fakeGateway';
import { TransactionRepository } from '../repositories/transactionRepository';
import { cardDeclined, notFound } from '../errors';
import { logger } from '../logger';

export interface ChargeInput {
  amount: number;
  currency: Currency;
  card: {
    number: string;
    expMonth: number;
    expYear: number;
    cvc: string;
  };
  customerId?: string;
}

export class PaymentsService {
  constructor(
    private readonly gateway: PaymentGateway,
    private readonly transactions: TransactionRepository,
  ) {}

  async charge(input: ChargeInput): Promise<Transaction> {
    assertPositiveAmount(input.amount);

    const result = await this.gateway.charge({
      amount: input.amount,
      currency: input.currency,
      card: input.card,
    });

    const transaction: Transaction = {
      id: `txn_${randomUUID()}`,
      amount: input.amount,
      currency: input.currency,
      status: result.approved ? 'succeeded' : 'failed',
      cardLast4: input.card.number.slice(-4),
      customerId: input.customerId,
      gatewayReference: result.gatewayReference,
      createdAt: new Date().toISOString(),
    };

    await this.transactions.save(transaction);

    logger.info(
      {
        transactionId: transaction.id,
        status: transaction.status,
        amount: transaction.amount,
        currency: transaction.currency,
      },
      'charge_processed',
    );

    if (!result.approved) {
      throw cardDeclined(result.declineReason ?? 'card_declined');
    }

    return transaction;
  }

  async getTransaction(id: string): Promise<Transaction> {
    const transaction = await this.transactions.findById(id);
    if (!transaction) throw notFound(`Transaction ${id} not found`);
    return transaction;
  }
}
