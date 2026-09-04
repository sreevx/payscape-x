# PAYSCAPE-X

### From payment success to business outcome.

> **A successful payment doesn't always mean a successful transaction.**

**PAYSCAPE-X** is a payment-outcome intelligence platform that looks beyond the payment itself.

It follows the journey:

**Customer Intent → Payment → Order → Inventory → Fulfillment → Delivery → Customer Outcome**

and answers a simple question:

> **Did the customer actually get what they paid for?**

---

## 🚀 Try the application

**Live Application:**
https://payscape-x-frontend.vercel.app

**GitHub:**
https://github.com/sreevx/payscape-x

---

## Why I built this

Most payment systems stop at:

**Payment → Success**

But a successful payment can still lead to:

* an out-of-stock product
* a failed fulfillment
* a delivery failure
* a cancelled order
* missing or contradictory events

The payment succeeded.

**The business transaction didn't.**

I wanted to build something that could see that difference.

That's where PAYSCAPE-X comes in.

---

## What PAYSCAPE-X does

PAYSCAPE-X reconstructs the complete transaction journey from the events available to it.

It then determines one of four outcomes:

| Outcome          | Meaning                                          |
| ---------------- | ------------------------------------------------ |
| **FULFILLED**    | The customer journey completed successfully      |
| **AT RISK**      | The transaction shows signs of potential failure |
| **FAILED**       | The business transaction did not complete        |
| **UNVERIFIABLE** | There isn't enough reliable evidence to decide   |

The important part is that **payment success alone is never treated as business success.**

---

## 🔎 How it works

```text
Raw Events
    ↓
Journey Reconstruction
    ↓
Evidence Engine
    ↓
Consistency Engine
    ↓
Business Outcome
    ↓
Failure & Impact Analysis
    ↓
Simulation
    ↓
AI Decision
    ↓
Human Approval
```

Each layer has a specific job.

The system first reconstructs what happened.

Then it checks what the available evidence actually supports.

Then it identifies the real business outcome.

For failures, it can trace the failure chain, identify the root cause, and understand its downstream impact.

---

## 🤖 AI, but with boundaries

My principle for PAYSCAPE-X is:

> **AI reasons. Code verifies.**

The AI Decision Agent doesn't get to freely invent actions.

It reasons over verified transaction context and can only select from a controlled set of actions.

Its output is validated by code.

If the AI output is invalid, the system falls back to deterministic rules.

And importantly:

**PAYSCAPE-X does not automatically move money.**

The flow stops at:

**REASON → RECOMMEND → HUMAN APPROVAL**

---

## 🧪 Simulation Lab

Sometimes the question isn't just:

> "What happened?"

It's:

> **"What could have been done differently?"**

PAYSCAPE-X includes a deterministic, read-only simulation layer that lets different interventions be compared against the current transaction state.

The simulations don't modify real transactions.

And simulated results are clearly labelled as **SIMULATED**.

---

## 💳 Razorpay integration

PAYSCAPE-X also supports **Razorpay TEST-MODE webhooks**.

Webhook events go through the same ingestion pipeline as the rest of the system.

They are:

* signature verified when configured
* normalized into the internal event model
* correlated with the correct transaction
* handled idempotently
* preserved when unknown

The integration is intentionally non-executing.

It records and analyzes events.

It does **not** perform real refunds, payments, or other financial actions.

---

## 🏗️ Tech stack

### Frontend

* Next.js
* React
* TypeScript
* Tailwind CSS
* shadcn/ui
* Lucide

### Backend

* FastAPI
* Python
* Pydantic
* SQLAlchemy
* Alembic
* PostgreSQL

### Infrastructure

* Vercel
* Railway
* Neon PostgreSQL

---

## 📊 Demo dataset

The application includes a deterministic dataset designed to exercise different transaction conditions.

It contains:

* **150** transaction journeys
* **100** customers
* **30** products
* **2,170** unified events
* **10** scenario types

Including:

* Normal success
* Payment failure
* Duplicate webhooks
* Delayed webhooks
* Inventory failure
* Delivery failure
* Refund flows
* Missing events
* Contradictory events
* Compound failures

---

## 🔐 Safety & reliability

PAYSCAPE-X is intentionally designed so that important decisions remain auditable.

The system keeps track of:

* evidence supporting a conclusion
* contradictions and missing information
* deterministic confidence
* failure chains
* impact reasoning
* simulation assumptions
* decision sources
* human approval state

The goal isn't to make AI look certain.

The goal is to make its decisions **understandable and verifiable**.

---

## 📁 Project structure

```text
payscape-x/
│
├── frontend/          # Next.js application
│
├── backend/
│   ├── app/
│   │   ├── api/       # API routes
│   │   ├── outcome/   # Business outcome engine
│   │   ├── failures/  # Compound failure analysis
│   │   ├── impact/    # Consequence & impact analysis
│   │   ├── simulation/# Simulation engine
│   │   ├── decision/  # AI decision layer
│   │   └── ingestion/ # Event ingestion
│   │
│   ├── alembic/       # Database migrations
│   └── tests/         # Backend tests
│
├── .env.example
├── README.md
└── .gitignore
```

---

## 🧑‍💻 Running locally

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Environment variables are documented in the provided `.env.example` files.

---

## Testing

Frontend:

```bash
cd frontend
npm run typecheck
npm run lint
npm test
```

Backend:

```bash
cd backend
pytest
```

---

## The idea in one line

**PAYSCAPE-X asks the question that payment systems often don't:**

> **The payment succeeded. But did the customer actually get what they paid for?**

---

### Built by Sreeved S

PAYSCAPE-X was designed and built as an individual project for the **Razorpay AI Buildathon 2026**.

**AI reasons. Code verifies.**
