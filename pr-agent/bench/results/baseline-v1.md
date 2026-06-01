## Run comparison

| version | PR | trials | cost (mean) | latency (mean) | findings | TP | precision | recall | F1 (mean +/- sd) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v1_single_shot | #1 | 1 | $0.1292 | 125.7s | 15.0 | 13.0/15 | 0.87 | 0.87 | 0.87 +/- 0.00 |
| v1_single_shot | #2 | 1 | $0.1496 | 126.9s | 12.0 | 11.0/14 | 0.92 | 0.79 | 0.85 +/- 0.00 |
| v1_single_shot | #3 | 1 | $0.2193 | 169.6s | 28.0 | 26.0/33 | 0.93 | 0.79 | 0.85 +/- 0.00 |

### PR #1 - issue hit rate (per version, X/trials)

| issue id | severity | category | v1_single_shot |
| --- | --- | --- | --- |
| pr1-security-card-pan-logged | must | security | 1/1 |
| pr1-quality-silent-error-swallow | must | quality | 1/1 |
| pr1-correctness-discount-always-zero | must | correctness | 1/1 |
| pr1-standards-snake-case-response | should | standards | 0/1 |
| pr1-correctness-coupon-not-validated | should | correctness | 1/1 |
| pr1-kiss-strategy-factory-overengineered | should | kiss | 1/1 |
| pr1-correctness-float-money | must | correctness | 1/1 |
| pr1-quality-bad-naming | should | quality | 1/1 |
| pr1-standards-var-instead-of-const | should | standards | 1/1 |
| pr1-standards-loose-equality | should | standards | 1/1 |
| pr1-quality-dead-code-comment | suggestion | quality | 1/1 |
| pr1-test-no-tests-added | should | test | 0/1 |
| pr1-quality-any-cast | should | quality | 1/1 |
| pr1-kiss-abstract-class-vs-interface | suggestion | kiss | 1/1 |
| pr1-quality-debug-log-coupon | should | quality | 1/1 |

### PR #2 - issue hit rate (per version, X/trials)

| issue id | severity | category | v1_single_shot |
| --- | --- | --- | --- |
| pr2-performance-history-in-memory-filter | must | performance | 1/1 |
| pr2-performance-n-plus-one-refund-enrich | must | performance | 1/1 |
| pr2-correctness-broken-sort-cents | should | correctness | 1/1 |
| pr2-security-card-pan-in-response | must | security | 1/1 |
| pr2-correctness-refund-amount-coercion | must | correctness | 1/1 |
| pr2-correctness-refund-no-amount-cap | should | correctness | 1/1 |
| pr2-quality-module-level-state | should | quality | 1/1 |
| pr2-correctness-zero-amount-refund | should | correctness | 0/1 |
| pr2-quality-console-log-business-events | should | quality | 0/1 |
| pr2-validation-loose-refund-schema | should | quality | 1/1 |
| pr2-correctness-refund-empty-200 | should | correctness | 1/1 |
| pr2-test-passes-for-wrong-reason | must | test | 1/1 |
| pr2-standards-response-naming-snake | suggestion | standards | 0/1 |
| pr2-security-customer-id-logged | should | security | 1/1 |

### PR #3 - issue hit rate (per version, X/trials)

| issue id | severity | category | v1_single_shot |
| --- | --- | --- | --- |
| pr3-security-env-committed | must | security | 1/1 |
| pr3-security-gitignore-override-env | must | security | 1/1 |
| pr3-security-jwt-secret-fallback | must | security | 0/1 |
| pr3-security-master-key-backdoor | must | security | 1/1 |
| pr3-security-jwt-no-algorithm-pin | should | security | 0/1 |
| pr3-security-predictable-reset-token | must | security | 0/1 |
| pr3-security-md5-password-hash | must | security | 1/1 |
| pr3-security-ts-nocheck | must | security | 1/1 |
| pr3-security-eval-in-where-clause | must | security | 1/1 |
| pr3-security-sql-injection-insert | must | security | 1/1 |
| pr3-security-find-user-logs-sql | must | security | 0/1 |
| pr3-security-listusers-arbitrary-filter | must | security | 0/1 |
| pr3-security-admin-bypass-query-flag | must | security | 1/1 |
| pr3-security-admin-by-email-suffix | must | security | 0/1 |
| pr3-dry-admin-role-check-duplicated | should | dry | 1/1 |
| pr3-security-webhook-ssrf | must | security | 1/1 |
| pr3-perf-webhook-sync-in-charge | must | performance | 0/1 |
| pr3-quality-webhook-fire-no-auth | must | security | 1/1 |
| pr3-security-store-pan-cvc | must | security | 1/1 |
| pr3-security-charge-logs-card | must | security | 1/1 |
| pr3-security-admin-filter-eval | must | security | 1/1 |
| pr3-security-csv-exports-pan | must | security | 1/1 |
| pr3-security-cors-wildcard-credentials | must | security | 1/1 |
| pr3-security-json-body-5mb | should | security | 1/1 |
| pr3-test-auth-tests-shallow | should | test | 1/1 |
| pr3-quality-controller-logs-pii | must | security | 1/1 |
| pr3-security-plaintext-password-logged | must | security | 1/1 |
| pr3-security-password-hash-in-response | must | security | 1/1 |
| pr3-security-jwt-no-expiry | must | security | 1/1 |
| pr3-security-user-enumeration | should | security | 1/1 |
| pr3-correctness-fakedb-delete-no-where | must | correctness | 1/1 |
| pr3-security-webhook-no-url-validation | should | security | 1/1 |
| pr3-perf-admin-no-pagination | should | performance | 1/1 |

Total API cost across 3 successful trials: $0.4981
