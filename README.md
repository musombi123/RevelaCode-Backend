# 🚀 RevelaCode Ecosystem

### One Platform • One Backend • One Identity • Multiple Hubs

RevelaCode is a modular digital ecosystem combining **faith, knowledge, education, agriculture, business, commerce, community and intelligent digital services** under one technology platform.

The ecosystem is built around a simple principle:

> **One RevelaCode identity can access multiple services without creating separate accounts.**

The existing RevelaCode platform remains intact while **Jumuiya** extends the backend with interconnected ecosystem hubs.

---

# 🌍 Ecosystem Overview

```text
                              REVELACODE ECOSYSTEM
                                      │
                         ONE IDENTITY • ONE BACKEND
                                      │
             ┌────────────────────────┴────────────────────────┐
             │                                                 │
      REVELACODE CORE                                      JUMUIYA
             │                                                 │
   ┌─────────┼──────────┐                    ┌─────────────────┼─────────────────┐
   │         │          │                    │                 │                 │
  BIBLE   PROPHECY    STUDY              BIASHARA           SHAMBA            ELIMU
   │         │          │                    │                 │                 │
   │         │          │                    └──────────┬──────┴──────┬──────────┘
   │         │          │                               │             │
   │         │          │                         MARKETPLACE       WALLET
   │         │          │                               │             │
   └─────────┴──────────┴───────────────────────────────┴──────┬──────┘
                                                               │
                                                          COMMUNITY
                                                               │
                                                               ▼
                                                      JUMUIYA ECOSYSTEM

 
## RevelaAI user verification

RevelaCode-Backend remains the only source of user identity. Login responses expose the existing MongoDB user ID as `id`, `user_id`, and `userId`; no new user records are created for RevelaAI.

Set `REVELAAI_VERIFY_KEY` in the backend deployment to a long, random service secret. Set the same value as `REVELACODE_VERIFY_KEY` in the RevelaAI service. The protected endpoint `GET /api/auth/verify/:userId` returns only whether that ObjectId exists in the authoritative `users` collection; it never returns the user's profile.

Keep `MONGO_URI` pointed at the existing Cluster0 and keep `MONGO_DB_NAME=revelacode`. RevelaAI uses the same cluster URI with its own database named `revelai`; do not change the backend's database name or grant RevelaAI direct access to `revelacode.users`.
