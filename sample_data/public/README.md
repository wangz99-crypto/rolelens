# RoleLens public demo data

These files provide the frozen sample data and RoleLens-authored context required by the local React and FastAPI demo.

`ibm_telco_customer_churn.csv` is the IBM-hosted sample Telco Customer Churn dataset distributed in the archived, read-only [`IBM/telco-customer-churn-on-icp4d`](https://github.com/IBM/telco-customer-churn-on-icp4d) repository at `data/Telco-Customer-Churn.csv`. The upstream repository is licensed under Apache License 2.0; its complete license is included here as `LICENSE-IBM-APACHE-2.0.txt`.

The local CSV contains 7,043 data rows and 21 columns. The redistributed CSV is byte-for-byte identical to `data/Telco-Customer-Churn.csv` at upstream commit `d5371f5d83a446ad5673cbcca3b814b926491f8a`. Its SHA-256 is `16320c9c1ec72448db59aa0a26a0b95401046bef5d02fd3aeb906448e3055e91`.

`ibm_telco_customer_churn_context.json` was authored for RoleLens. Its business question, strategy context, and scenario assumptions are demo metadata, not observed facts from the IBM-hosted dataset and not upstream IBM artifacts.

This is fictional/sample data, not RoleLens production customer data. The RoleLens demo performs no individual customer targeting.
