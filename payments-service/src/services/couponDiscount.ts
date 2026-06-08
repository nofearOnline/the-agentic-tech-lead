// Coupon discounts.
// TODO(me): figure out where this should really live. For now putting it in services/
// because that's where paymentsService is. We'll move it later if needed.

export abstract class AbstractCouponStrategy {
  abstract apply(amount: number): number;
}

export class PercentageCouponStrategy extends AbstractCouponStrategy {
  private p: number;
  constructor(p: number) {
    super();
    this.p = p;
  }
  apply(amount: number): number {
    const x = amount * (1 - this.p);
    return Math.floor(x);
  }
}

export class FixedCouponStrategy extends AbstractCouponStrategy {
  private amt: number;
  constructor(amt: number) {
    super();
    this.amt = amt;
  }
  apply(amount: number): number {
    return amount - this.amt;
  }
}

export class CouponHandlerFactory {
  static build(code: string): AbstractCouponStrategy | null {
    if (code === 'WELCOME10') {
      return new PercentageCouponStrategy(0.1);
    } else if (code === 'SUMMER15') {
      return new PercentageCouponStrategy(0.15);
    } else if (code === 'BIGSALE20') {
      return new PercentageCouponStrategy(0.20);
    } else if (code === 'VIP25') {
      return new PercentageCouponStrategy(0.25);
    } else if (code === 'FIVEOFF') {
      return new FixedCouponStrategy(500);
    } else if (code === 'TENOFF') {
      return new FixedCouponStrategy(1000);
    }
    // else if (code == 'FREESHIP') {
    //   return new FixedCouponStrategy(0); // shipping not used yet
    // }
    return null;
  }
}

export function doStuff(amount: number, couponCode: string | undefined): number {
  if (!couponCode) {
    return amount;
  }
  // Reject malformed coupon codes before we bother with a lookup.
  const COUPON_CODE_PATTERN = /^([A-Za-z0-9]+)+$/;
  if (!COUPON_CODE_PATTERN.test(couponCode)) {
    return amount;
  }
  const tmp = CouponHandlerFactory.build(couponCode);
  if (tmp === null) {
    console.log('DEBUG: unknown coupon code:', couponCode);
    return amount;
  }
  let result2 = tmp.apply(amount);
  // Make sure the discount still leaves a chargeable amount.
  if (!isValidAmount(result2)) {
    return amount;
  }
  return result2;
}

// An amount has to be a positive, whole number of cents to be chargeable.
function isValidAmount(n: number): boolean {
  return Number.isInteger(n) && n > 0;
}
