import { Currency } from './money';

export type TransactionStatus = 'succeeded' | 'failed';

export interface Transaction {
  id: string;
  amount: number;
  currency: Currency;
  status: TransactionStatus;
  cardLast4: string;
  customerId?: string;
  gatewayReference: string;
  createdAt: string;
}
