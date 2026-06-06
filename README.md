# Clinic Management API

A production-style clinic management REST API built with FastAPI.
Consolidates all core Python topics into a single cohesive application —
from OOP domain models and SQL transactions to NumPy analytics and JWT-secured endpoints.

---

## What It Does

The API manages the full lifecycle of a clinic:

- **Doctors** — register, list, and retrieve physicians with computed salary and seniority
- **Patients** — full CRUD with PHI-masked responses and role-based write access
- **Appointments** — create, list (joined with patient and doctor names), and update status
- **Analytics** — NumPy risk scoring and Pandas reporting exposed as a single endpoint
- **Auth** — JWT-based login with bcrypt password hashing and role enforcement

---

## Architecture

```
Incoming Request
       │
       ▼
┌─────────────────┐
│   Middleware    │  Logs method · path · status · latency on every request
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ JWT Verification│  verify_token() injected via Depends() — 401 on failure
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Role Check     │  require_doctor() chains on top of verify_token() — 403 on failure
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Route Handler   │  Pydantic validates input — 422 on bad data
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ PHI Protection  │  sanitize_phi() masks phone and email before every response
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Audit Log      │  logger.info() records every significant action
└─────────────────┘
```

---

## API Reference

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/auth/register` | — | Create a new user account |
| `POST` | `/auth/login` | — | Authenticate and receive a JWT |

### Doctors

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/doctors` | ✅ Bearer | Add a new doctor |
| `GET` | `/doctors` | ✅ Bearer | List all doctors with computed salary and seniority |
| `GET` | `/doctors/{id}` | ✅ Bearer | Retrieve one doctor |

### Patients

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/patients` | 🔒 Doctor | Register a new patient |
| `GET` | `/patients` | ✅ Bearer | List patients — PHI masked |
| `GET` | `/patients/{id}` | ✅ Bearer | Retrieve one patient — PHI masked |
| `PATCH` | `/patients/{id}` | 🔒 Doctor | Partially update a patient |
| `DELETE` | `/patients/{id}` | 🔒 Doctor | Remove a patient |

### Appointments

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/appointments` | ✅ Bearer | Schedule an appointment |
| `GET` | `/appointments` | ✅ Bearer | List all appointments with patient and doctor names |
| `PATCH` | `/appointments/{id}` | ✅ Bearer | Update appointment status |

### System

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/analytics` | ✅ Bearer | NumPy risk scores + Pandas report |
| `GET` | `/health` | — | Record counts for monitoring tools |

---

## Topics Covered

**Python Fundamentals**
- f-strings, list comprehension, dict operations, sorted + lambda

**OOP**
- `Person` base class → `Doctor` and `Patient` via inheritance and `super()`
- `@property` for BMI, salary, experience_level, age_group
- `@classmethod` factory method `Doctor.from_dict()`
- `@dataclass` for `Appointment` — auto-generated `__init__` and `__repr__`

**Advanced Python**
- `DatabaseConnection` context manager — automatic commit/rollback/close
- `logging` module — structured operation tracking

**SQL**
- 4-table schema with `FOREIGN KEY` constraints
- `INNER JOIN` across three tables in the appointments list query
- Parameterised `?` placeholders throughout — SQL injection safe
- Dynamic `UPDATE` built from `model_dump(exclude_none=True)`
- `rowcount` to distinguish "not found" from "deleted"

**NumPy**
- Vectorized BMI and risk score calculation — no Python loops
- Boolean masking for high-risk patient count
- `np.clip()`, `np.where()`, `np.argmax()`, `np.percentile()`

**Pandas**
- `pd.DataFrame()` from a list of dicts
- `apply()` + lambda for risk classification
- `value_counts()` for category distribution
- `to_csv()` for report export

**Security**
- `bcrypt` with per-password salt — plain text never stored
- JWT (HS256) — 24-hour expiry, role embedded in payload
- `Depends()` dependency injection — layered auth in one line
- PHI masking on phone and email before every patient response
- Generic "Invalid credentials" error — username enumeration prevented

**FastAPI**
- Path parameters, query parameters, request body
- Pydantic models with `Field(gt, lt, ge, le)` constraints
- `response_model` — sensitive fields stripped automatically
- `model_dump(exclude_none=True)` for safe partial updates
- `HTTPException` with appropriate status codes
- `@app.middleware("http")` for request logging

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI 0.115+ |
| Validation | Pydantic v2 |
| Server | Uvicorn |
| Auth | PyJWT (HS256) |
| Hashing | bcrypt |
| Database | SQLite (sqlite3) |
| Secrets | python-dotenv |
| Analytics | NumPy + Pandas |

---

## Getting Started

```bash
git clone https://github.com/volkancelebidev/clinic-management-api.git
cd clinic-management-api
pip install fastapi uvicorn pydantic bcrypt PyJWT python-dotenv numpy pandas
```

Create `.env` in the project root:

```env
SECRET_KEY=your-secret-key-here
```

Start the server:

```bash
uvicorn main:app --reload
```

| URL | Description |
|-----|-------------|
| `http://127.0.0.1:8000/docs` | Swagger UI — interactive explorer |
| `http://127.0.0.1:8000/redoc` | ReDoc — clean documentation |
| `http://127.0.0.1:8000/health` | Health check |

---

## Project Structure

```
clinic-management-api/
├── main.py        # Complete API — all routes, models, and security
├── .env           # Secret keys (not committed)
└── .gitignore
```

> A production deployment would split this into `routers/`, `models/`,
> `schemas/`, `core/security.py`, and `db/` directories. The single-file
> structure is intentional here to keep the full request lifecycle visible
> in one place.

---

## Compliance Notes

| Regulation | Controls Applied |
|------------|-----------------|
| **GDPR** (EU) | PHI masking on all patient responses, audit log per access |
| **KVKK** (Turkey) | Same controls as GDPR — directly applicable |
| **HIPAA** (US) | PHI access logging, bcrypt storage, role-based access |

---

## What I Learned

- Building a layered security pipeline with FastAPI `Depends()`
- Chaining `require_doctor()` on top of `verify_token()` for role-based access
- Using Pydantic `response_model` to automatically strip sensitive fields
- Writing safe partial updates with `model_dump(exclude_none=True)`
- Implementing dynamic SQL `UPDATE` that only touches supplied columns
- Applying `@property` chains where `bmi_category` depends on `bmi`
- Running vectorized NumPy risk scoring without a single Python loop
- Combining `groupby`, `apply`, and `value_counts` in a Pandas analytics pipeline
