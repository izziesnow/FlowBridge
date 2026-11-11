# Design note: Move the taxpayer portal login to the new database cluster

Request: GOV-015
Document version: 1
Prepared by: Safiya Isah
Date: 29 October 2026

## Summary
Existing records are not modified; new fields default to empty for older records. Configuration is held in the environment, so the change can be switched off without a redeploy. The change is limited to the taxpayer portal login and does not alter any shared database tables.

## Changes in this version
First issue.

---
Synthetic document for the fictional organisation Zenkora Technologies Limited (ZTL).
