export type Currency = 'USD' | 'EUR' | 'GBP';

export const SUPPORTED_CURRENCIES: readonly Currency[] = ['USD', 'EUR', 'GBP'];

export interface Money {
  amount: number;
  currency: Currency;
}

export function isSupportedCurrency(value: string): value is Currency {
  return (SUPPORTED_CURRENCIES as readonly string[]).includes(value);
}

export function assertPositiveAmount(amount: number): void {
  if (!Number.isInteger(amount) || amount <= 0) {
    throw new Error(`Amount must be a positive integer in the smallest currency unit, got ${amount}`);
  }
}
