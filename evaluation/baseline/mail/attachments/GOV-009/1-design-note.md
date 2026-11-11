# Design note: Cache lookups in the TIN validation

Request: GOV-009
Document version: 1
Prepared by: Stephen Balogun
Date: 11 September 2026

## Summary
Existing records are not modified; new fields default to empty for older records. This document describes the change, the components it touches and how it will be tested. Configuration is held in the environment, so the change can be switched off without a redeploy.

## Changes in this version
First issue.

---
Synthetic document for the fictional organisation Zenkora Technologies Limited (ZTL).
