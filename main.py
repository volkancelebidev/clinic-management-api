"""
main.py — Clinic Management System

A production-style clinic API that consolidates all topics covered so far:

    Python Fundamentals → f-string, list comprehension, dict, sorted, lambda
    OOP                 → inheritance, @property, @classmethod, __repr__, @dataclass
    Advanced Python     → decorator, context manager, generator, logging
    SQL                 → 4-table schema, INNER JOIN, parametric queries, transactions
    NumPy               → array, vectorization, boolean masking, statistics
    Pandas              → DataFrame, groupby, merge, apply, value_counts, to_csv
    Security            → bcrypt, JWT, PHI masking, input validation
    FastAPI             → endpoints, Pydantic, Depends, middleware, HTTPException

Run:
    uvicorn main:app --reload

Explore:
    http://127.0.0.1:8000/docs
"""

import os
import re
import time
import sqlite3
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

import bcrypt
import jwt
import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# All secrets come from .env — never hardcoded.
# Fail-fast: the application refuses to start if SECRET_KEY is missing.

load_dotenv()

logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt= "%H:%M:%S",
)
logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "clinic_secret_key")
ALGORITHM  = "HS256"
DB_PATH    = "clinic.db"

if not SECRET_KEY:
    raise ValueError("SECRET_KEY is not set. Add it to your .env file.")

app    = FastAPI(title="Clinic Management API", version="1.0.0")
bearer = HTTPBearer()   # reads Authorization: Bearer <token> header


# ---------------------------------------------------------------------------
# Database — Context Manager
# ---------------------------------------------------------------------------
# __enter__ opens the connection and returns it to the with block.
# __exit__ commits on clean exit, rolls back on exception, always closes.
# row_factory enables column-name access: row["name"] instead of row[0].
# PRAGMA foreign_keys must be set per connection — SQLite default is OFF.


class DatabaseConnection:
    """Managed SQLite connection with automatic commit/rollback/close."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn    = None

    def __enter__(self) -> sqlite3.Connection:
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self.conn.rollback()
            logger.error("Transaction rolled back: %s", exc_val)
        else:
            self.conn.commit()
        self.conn.close()


def init_db() -> None:
    """Create the four-table schema if it does not already exist.

    executescript() runs in autocommit mode — required for PRAGMA to work.
    DROP order matters: dependent tables must be listed before referenced ones.
    CREATE TABLE IF NOT EXISTS makes the function safe to call on every restart.
    """
    with DatabaseConnection(DB_PATH) as conn:
        conn.executescript("""
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS users (
                user_id       TEXT PRIMARY KEY,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'nurse'
            );

            CREATE TABLE IF NOT EXISTS doctors (
                doctor_id    TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                age          INTEGER NOT NULL,
                specialty    TEXT NOT NULL,
                department   TEXT NOT NULL,
                max_patients INTEGER DEFAULT 30
            );

            CREATE TABLE IF NOT EXISTS patients (
                patient_id  TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                age         INTEGER NOT NULL,
                email       TEXT,
                phone       TEXT,
                blood_type  TEXT,
                weight      REAL DEFAULT 0,
                height      REAL DEFAULT 0,
                diagnosis   TEXT,
                admitted_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS appointments (
                appt_id    TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL REFERENCES patients(patient_id),
                doctor_id  TEXT NOT NULL REFERENCES doctors(doctor_id),
                appt_date  TEXT NOT NULL,
                reason     TEXT,
                status     TEXT NOT NULL DEFAULT 'Scheduled'
            );
        """)


init_db()


# ---------------------------------------------------------------------------
# OOP — Domain models
# ---------------------------------------------------------------------------
# Person is the base class; Doctor and Patient extend it via inheritance.
# super().__init__() delegates shared fields to the parent so they are not
# duplicated in every subclass.
# @property computes a value on every access — no manual recalculation needed.
# @classmethod is called on the class itself: Doctor.from_dict(data).
# @dataclass auto-generates __init__ and __repr__ for data-only classes.


class Person:
    """Base class for all people registered in the system."""

    def __init__(self, person_id: str, name: str, age: int) -> None:
        self.person_id = person_id
        self.name      = name
        self.age       = age

    @property
    def age_group(self) -> str:
        """Demographic tier derived from age — updates automatically."""
        if self.age >= 60:
            return "Senior"
        if self.age >= 40:
            return "Middle-aged"
        return "Young"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.person_id!r}, name={self.name!r})"


class Doctor(Person):
    """A physician extending Person with clinical attributes."""

    def __init__(self, person_id: str, name: str, age: int,
                 specialty: str, department: str, max_patients: int = 30) -> None:
        super().__init__(person_id, name, age)   # delegate to Person
        self.specialty    = specialty
        self.department   = department
        self.max_patients = max_patients

    @property
    def salary(self) -> float:
        """Computed salary — updates if age changes."""
        return 4000 + (self.age * 100)

    @property
    def experience_level(self) -> str:
        """Seniority tier based on age."""
        if self.age >= 50:
            return "Senior Specialist"
        if self.age >= 35:
            return "Specialist"
        return "Resident"

    @classmethod
    def from_dict(cls, data: dict) -> "Doctor":
        """Factory method — build a Doctor from a plain dict.

        Called as Doctor.from_dict(row) rather than Doctor(...).
        Useful when loading records from the database or an API response.
        """
        return cls(
            person_id    = data["doctor_id"],
            name         = data["name"],
            age          = data["age"],
            specialty    = data["specialty"],
            department   = data["department"],
            max_patients = data.get("max_patients", 30),
        )


class Patient(Person):
    """A patient extending Person with clinical measurements."""

    def __init__(self, person_id: str, name: str, age: int,
                 email: str = "", phone: str = "", blood_type: str = "",
                 weight: float = 0.0, height: float = 0.0,
                 diagnosis: str = "") -> None:
        super().__init__(person_id, name, age)
        self.email      = email
        self.phone      = phone
        self.blood_type = blood_type
        self.weight     = weight
        self._height    = height   # underscore → exposed only through bmi property
        self.diagnosis  = diagnosis

    @property
    def bmi(self) -> float:
        """BMI computed from current weight and height."""
        if self._height <= 0:
            return 0.0
        return round(self.weight / ((self._height / 100) ** 2), 1)

    @property
    def bmi_category(self) -> str:
        """Clinical weight classification — chains the bmi property."""
        if self.bmi <= 0:
            return "Unknown"
        if self.bmi >= 30:
            return "Obese"
        if self.bmi >= 25:
            return "Overweight"
        if self.bmi >= 18.5:
            return "Normal"
        return "Underweight"


@dataclass
class Appointment:
    """Appointment data class — __init__ and __repr__ are auto-generated.

    Used for data-only objects where @property and @classmethod are not needed.
    is_valid_status() is a regular method added on top of the dataclass.
    """

    appt_id   : str
    patient_id: str
    doctor_id : str
    appt_date : str
    reason    : str = ""
    status    : str = "Scheduled"
    VALID_STATUSES = ("Scheduled", "Completed", "Cancelled", "No-show")

    def is_valid_status(self, new_status: str) -> bool:
        """Return True if new_status is one of the allowed values."""
        return new_status in self.VALID_STATUSES


# ---------------------------------------------------------------------------
# Security — Password hashing
# ---------------------------------------------------------------------------
# bcrypt is a one-way hash function — the original password cannot be recovered.
# gensalt() generates a unique random salt per password, defeating rainbow tables.
# verify_password re-hashes the plain text with the stored salt and compares.


def hash_password(password: str) -> bytes:
    """Hash a plain-text password with bcrypt. Called at registration only."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def verify_password(plain: str, hashed: bytes) -> bool:
    """Compare a plain-text attempt against a stored bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed)


# ---------------------------------------------------------------------------
# Security — JWT
# ---------------------------------------------------------------------------
# The token carries user identity and role so endpoints can authorise
# without a database lookup on every request.
# exp (expiry) limits the exposure window if a token is intercepted.


def create_token(user_id: str, role: str) -> str:
    """Issue a signed JWT valid for 24 hours."""
    payload = {
        "user_id": user_id,
        "role"   : role,
        "exp"    : datetime.now(timezone.utc) + timedelta(hours=24),
        "iat"    : datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ---------------------------------------------------------------------------
# Security — PHI protection
# ---------------------------------------------------------------------------
# GDPR, KVKK, and HIPAA require that phone numbers and email addresses
# are masked before leaving the API in any response or log entry.


def mask_phone(phone: str) -> str:
    """Mask all but the last four digits of a phone number."""
    if not phone or len(phone) <= 4:
        return "****"
    return "*" * (len(phone) - 4) + phone[-4:]


def mask_email(email: str) -> str:
    """Mask the username portion of an email address."""
    if not email or "@" not in email:
        return "***@***.***"
    parts = email.split("@")
    return f"{parts[0][:2]}{'*' * max(0, len(parts[0]) - 2)}@{parts[1]}"


def sanitize_phi(patient: dict) -> dict:
    """Mask sensitive fields before including a patient in an API response.

    .copy() prevents the original dict from being mutated.
    .pop(key, None) removes the key silently if it does not exist.
    """
    safe = patient.copy()
    if safe.get("phone"):
        safe["phone"] = mask_phone(safe["phone"])
    if safe.get("email"):
        safe["email"] = mask_email(safe["email"])
    safe.pop("password_hash", None)
    return safe


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
# @app.middleware("http") wraps every request/response cycle.
# async def and await are required because FastAPI is ASGI-based.
# call_next forwards the request to the next handler and suspends
# this coroutine until a response is ready — other requests are not blocked.
# % format strings are preferred over f-strings in logging: the string is
# only built if the message will actually be emitted (performance).


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log method, path, status code, and latency for every request."""
    start    = time.time()
    response = await call_next(request)
    elapsed  = time.time() - start
    logger.info(
        "%s %s → %d (%.3fs)",
        request.method, request.url.path, response.status_code, elapsed,
    )
    return response


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
# BaseModel validates incoming data automatically — wrong types return 422.
# Field(gt=0, lt=150) adds numeric constraints on top of the type check.
# str | None = None marks a field as optional with a None default, used
# in PATCH models so only supplied fields are written to the database.
# response_model strips undeclared fields — password_hash never appears.


class UserCreate(BaseModel):
    user_id : str
    username: str
    email   : str
    password: str
    role    : str = "nurse"


class UserLogin(BaseModel):
    username: str
    password: str


class DoctorCreate(BaseModel):
    doctor_id   : str
    name        : str
    age         : int = Field(gt=20, lt=80)
    specialty   : str
    department  : str
    max_patients: int = Field(default=30, gt=0, le=100)


class PatientCreate(BaseModel):
    patient_id: str
    name      : str
    age       : int   = Field(gt=0, lt=150)
    email     : str   = ""
    phone     : str   = ""
    blood_type: str   = ""
    weight    : float = Field(default=0.0, ge=0)
    height    : float = Field(default=0.0, ge=0)
    diagnosis : str   = ""


class PatientUpdate(BaseModel):
    """All fields optional — only supplied fields are written to the database."""
    name      : str   | None = None
    age       : int   | None = Field(default=None, gt=0, lt=150)
    email     : str   | None = None
    phone     : str   | None = None
    blood_type: str   | None = None
    diagnosis : str   | None = None


class AppointmentCreate(BaseModel):
    appt_id   : str
    patient_id: str
    doctor_id : str
    appt_date : str
    reason    : str = ""


class AppointmentUpdate(BaseModel):
    status: str


class PatientResponse(BaseModel):
    """Response model — password_hash is absent so it never leaves the API."""
    patient_id: str
    name      : str
    age       : int
    email     : str = ""
    phone     : str = ""
    blood_type: str = ""
    diagnosis : str = ""


class TokenResponse(BaseModel):
    access_token: str
    token_type  : str = "bearer"
    role        : str


# ---------------------------------------------------------------------------
# Dependency injection — JWT
# ---------------------------------------------------------------------------
# Depends() tells FastAPI to run a function before the route handler.
# verify_token reads the Bearer token, decodes it, and returns the payload.
# If the token is invalid, FastAPI returns 401 and the handler never runs.
# require_doctor chains verify_token with a role check — two layers in one.


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    """Validate the JWT from the Authorization header and return its payload.

    Depends(bearer) extracts the token automatically from the header.
    Raises 401 if the token is expired or structurally invalid.
    """
    try:
        return jwt.decode(
            credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


def require_doctor(payload: dict = Depends(verify_token)) -> dict:
    """Extend verify_token with a role check for doctor-only endpoints.

    Depends(verify_token) runs first — token must be valid before the role
    is inspected.  Raises 403 if the authenticated user is not a doctor.
    """
    if payload.get("role") != "doctor":
        raise HTTPException(status_code=403, detail="Only doctors can perform this action.")
    return payload


# ---------------------------------------------------------------------------
# Routes — Authentication
# ---------------------------------------------------------------------------


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(user: UserCreate):
    """Register a new user account.

    Validates email format and minimum password length before hashing.
    INSERT raises IntegrityError on duplicate username — mapped to 409.
    """
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", user.email):
        raise HTTPException(status_code=422, detail="Invalid email format.")
    if len(user.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters.")

    hashed = hash_password(user.password)

    with DatabaseConnection(DB_PATH) as conn:
        try:
            conn.execute(
                "INSERT INTO users (user_id, username, password_hash, role) VALUES (?, ?, ?, ?)",
                (user.user_id, user.username, hashed, user.role),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail=f"Username {user.username!r} already exists.")

    logger.info("User registered: %s (%s)", user.username, user.role)
    return {"message": f"User {user.username!r} registered successfully."}


@app.post("/auth/login", response_model=TokenResponse)
def login(credentials: UserLogin):
    """Authenticate a user and return a signed JWT.

    The error message is intentionally generic — revealing which field
    failed would help an attacker enumerate valid usernames.
    """
    with DatabaseConnection(DB_PATH) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (credentials.username,),
        ).fetchone()

    if not row or not verify_password(credentials.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    token = create_token(row["user_id"], row["role"])
    logger.info("User logged in: %s", credentials.username)
    return TokenResponse(access_token=token, role=row["role"])


# ---------------------------------------------------------------------------
# Routes — Doctors
# ---------------------------------------------------------------------------


@app.post("/doctors", status_code=status.HTTP_201_CREATED)
def add_doctor(doctor: DoctorCreate, payload: dict = Depends(verify_token)):
    """Add a new doctor. INSERT OR IGNORE silently skips duplicate IDs."""
    with DatabaseConnection(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO doctors "
            "(doctor_id, name, age, specialty, department, max_patients) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (doctor.doctor_id, doctor.name, doctor.age,
             doctor.specialty, doctor.department, doctor.max_patients),
        )
    logger.info("Doctor added: %s", doctor.name)
    return {"message": f"Doctor {doctor.name!r} added."}


@app.get("/doctors")
def list_doctors(payload: dict = Depends(verify_token)):
    """Return all doctors enriched with computed @property values.

    Doctor.from_dict() builds an OOP object from each database row so
    experience_level and salary (both @property) can be included in the
    response without storing them in the database.
    """
    with DatabaseConnection(DB_PATH) as conn:
        rows = conn.execute("SELECT * FROM doctors ORDER BY name").fetchall()

    result = []
    for row in rows:
        d   = dict(row)
        doc = Doctor.from_dict(d)
        result.append({
            **d,
            "experience_level": doc.experience_level,
            "salary"          : doc.salary,
            "age_group"       : doc.age_group,
        })
    return result


@app.get("/doctors/{doctor_id}")
def get_doctor(doctor_id: str, payload: dict = Depends(verify_token)):
    """Retrieve a single doctor by primary key. Returns 404 if not found."""
    with DatabaseConnection(DB_PATH) as conn:
        row = conn.execute(
            "SELECT * FROM doctors WHERE doctor_id = ?", (doctor_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Doctor {doctor_id!r} not found.")

    d   = dict(row)
    doc = Doctor.from_dict(d)
    return {**d, "experience_level": doc.experience_level, "salary": doc.salary}


# ---------------------------------------------------------------------------
# Routes — Patients
# ---------------------------------------------------------------------------


@app.post("/patients", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(patient: PatientCreate, payload: dict = Depends(require_doctor)):
    """Register a new patient. Restricted to doctor role."""
    with DatabaseConnection(DB_PATH) as conn:
        try:
            conn.execute(
                "INSERT INTO patients "
                "(patient_id, name, age, email, phone, blood_type, "
                "weight, height, diagnosis, admitted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (patient.patient_id, patient.name, patient.age,
                 patient.email, patient.phone, patient.blood_type,
                 patient.weight, patient.height, patient.diagnosis,
                 datetime.now().strftime("%Y-%m-%d")),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail=f"Patient {patient.patient_id!r} already exists.")

    logger.info("Patient created: %s by %s", patient.patient_id, payload["user_id"])
    return patient


@app.get("/patients", response_model=list[PatientResponse])
def list_patients(limit: int = 20, payload: dict = Depends(verify_token)):
    """Return a paginated, PHI-masked patient list."""
    with DatabaseConnection(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT * FROM patients ORDER BY name LIMIT ?", (limit,)
        ).fetchall()
    return [sanitize_phi(dict(row)) for row in rows]


@app.get("/patients/{patient_id}", response_model=PatientResponse)
def get_patient(patient_id: str, payload: dict = Depends(verify_token)):
    """Retrieve a single patient with PHI masking. Validates P### format."""
    if not re.match(r"^P\d{3}$", patient_id):
        raise HTTPException(status_code=422, detail=f"Invalid patient ID: {patient_id!r}.")

    with DatabaseConnection(DB_PATH) as conn:
        row = conn.execute(
            "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id!r} not found.")

    logger.info("Patient accessed: %s by %s", patient_id, payload["user_id"])
    return sanitize_phi(dict(row))


@app.patch("/patients/{patient_id}", response_model=PatientResponse)
def update_patient(
    patient_id: str,
    update    : PatientUpdate,
    payload   : dict = Depends(require_doctor),
):
    """Partially update a patient. Only supplied fields are written.

    model_dump(exclude_none=True) drops None values so a caller sending
    only {"age": 55} does not accidentally overwrite other columns with NULL.
    The UPDATE clause is built dynamically from the supplied keys.
    """
    with DatabaseConnection(DB_PATH) as conn:
        row = conn.execute(
            "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id!r} not found.")

    update_data = update.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=422, detail="No fields provided for update.")

    set_clause = ", ".join(f"{k} = ?" for k in update_data)
    values     = list(update_data.values()) + [patient_id]

    with DatabaseConnection(DB_PATH) as conn:
        conn.execute(f"UPDATE patients SET {set_clause} WHERE patient_id = ?", values)
        updated = conn.execute(
            "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)
        ).fetchone()

    logger.info("Patient updated: %s by %s", patient_id, payload["user_id"])
    return sanitize_phi(dict(updated))


@app.delete("/patients/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patient(patient_id: str, payload: dict = Depends(require_doctor)):
    """Delete a patient permanently. Returns 204 on success, 404 if not found.

    rowcount == 0 means the WHERE clause matched no rows.
    """
    with DatabaseConnection(DB_PATH) as conn:
        result = conn.execute(
            "DELETE FROM patients WHERE patient_id = ?", (patient_id,)
        )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id!r} not found.")

    logger.info("Patient deleted: %s by %s", patient_id, payload["user_id"])


# ---------------------------------------------------------------------------
# Routes — Appointments
# ---------------------------------------------------------------------------


@app.post("/appointments", status_code=status.HTTP_201_CREATED)
def create_appointment(appt: AppointmentCreate, payload: dict = Depends(verify_token)):
    """Create an appointment. FOREIGN KEY constraints prevent orphaned records."""
    with DatabaseConnection(DB_PATH) as conn:
        try:
            conn.execute(
                "INSERT INTO appointments "
                "(appt_id, patient_id, doctor_id, appt_date, reason) "
                "VALUES (?, ?, ?, ?, ?)",
                (appt.appt_id, appt.patient_id, appt.doctor_id,
                 appt.appt_date, appt.reason),
            )
        except sqlite3.IntegrityError as e:
            raise HTTPException(status_code=409, detail=str(e))

    return {"message": f"Appointment {appt.appt_id!r} created."}


@app.get("/appointments")
def list_appointments(payload: dict = Depends(verify_token)):
    """Return all appointments joined with patient and doctor names.

    INNER JOIN — only rows that have a match in both tables are returned.
    AS aliases rename columns so patient name and doctor name do not clash.
    """
    with DatabaseConnection(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT
                a.appt_id,
                a.appt_date,
                a.reason,
                a.status,
                p.name AS patient_name,
                p.age  AS patient_age,
                d.name AS doctor_name,
                d.specialty
            FROM appointments a
            INNER JOIN patients p ON a.patient_id = p.patient_id
            INNER JOIN doctors  d ON a.doctor_id  = d.doctor_id
            ORDER BY a.appt_date DESC
        """).fetchall()

    return [dict(row) for row in rows]


@app.patch("/appointments/{appt_id}")
def update_appointment(
    appt_id: str,
    update : AppointmentUpdate,
    payload: dict = Depends(verify_token),
):
    """Update appointment status. Uses Appointment.is_valid_status() for validation."""
    dummy = Appointment(appt_id=appt_id, patient_id="", doctor_id="", appt_date="")
    if not dummy.is_valid_status(update.status):
        raise HTTPException(
            status_code = 422,
            detail      = f"Invalid status. Must be one of {Appointment.VALID_STATUSES}.",
        )

    with DatabaseConnection(DB_PATH) as conn:
        result = conn.execute(
            "UPDATE appointments SET status = ? WHERE appt_id = ?",
            (update.status, appt_id),
        )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Appointment {appt_id!r} not found.")

    return {"message": f"Appointment {appt_id!r} updated to {update.status!r}."}


# ---------------------------------------------------------------------------
# Analytics — NumPy + Pandas
# ---------------------------------------------------------------------------


def numpy_analytics(patients: list[dict]) -> dict:
    """Compute vectorized statistics and risk scores with NumPy.

    All calculations apply to the entire array simultaneously — no Python loops.
    Boolean masking counts patients that exceed a threshold without a loop.
    np.argmax/argmin return the index of the extreme value.
    """
    if not patients:
        return {}

    ages    = np.array([p["age"]                    for p in patients])
    weights = np.array([p.get("weight", 70) or 70   for p in patients])
    heights = np.array([p.get("height", 170) or 170 for p in patients])

    heights_m   = heights / 100
    bmis        = np.where(heights_m > 0, np.round(weights / (heights_m ** 2), 1), 0.0)
    norm_age    = np.clip(ages / 100, 0, 1)
    norm_bmi    = np.clip((bmis - 18.5) / 21.5, 0, 1)
    risk_scores = np.round((norm_age * 0.4 + norm_bmi * 0.6) * 100, 1)

    return {
        "total"          : len(patients),
        "age_mean"       : round(float(np.mean(ages)),   1),
        "age_median"     : round(float(np.median(ages)), 1),
        "age_std"        : round(float(np.std(ages)),    1),
        "avg_bmi"        : round(float(np.mean(bmis)),   1),
        "high_risk_count": int(np.sum(risk_scores > 60)),
        "highest_risk"   : patients[int(np.argmax(risk_scores))]["name"],
    }


def pandas_report(patients: list[dict]) -> dict:
    """Analyse patient data with Pandas.

    pd.DataFrame() builds the table from a list of dicts.
    apply() + lambda assigns a risk label to every row without a loop.
    value_counts() counts occurrences of each category.
    to_csv() exports the enriched dataset for downstream use.
    """
    if not patients:
        return {}

    df = pd.DataFrame(patients)
    df["height_m"] = df["height"].replace(0, 170) / 100
    df["bmi"]      = (df["weight"].replace(0, 70) / (df["height_m"] ** 2)).round(1)
    df = df.drop(columns=["height_m"])

    df["risk_level"] = df["bmi"].apply(
        lambda bmi: "High" if bmi >= 30 else ("Medium" if bmi >= 25 else "Normal")
    )

    df.to_csv("clinic_report.csv", index=False)

    return {
        "total_patients"   : len(df),
        "avg_age"          : round(df["age"].mean(), 1),
        "avg_bmi"          : round(df["bmi"].mean(), 1),
        "risk_distribution": df["risk_level"].value_counts().to_dict(),
    }


@app.get("/analytics")
def get_analytics(payload: dict = Depends(verify_token)):
    """Run NumPy and Pandas analytics on all registered patients."""
    with DatabaseConnection(DB_PATH) as conn:
        rows = conn.execute("SELECT * FROM patients").fetchall()

    patients = [dict(row) for row in rows]
    if not patients:
        return {"message": "No patients found."}

    return {
        "numpy"  : numpy_analytics(patients),
        "pandas" : pandas_report(patients),
    }


# ---------------------------------------------------------------------------
# Routes — System
# ---------------------------------------------------------------------------


@app.get("/health")
def health_check():
    """Return record counts for monitoring tools.

    Intentionally unauthenticated — monitoring agents do not carry tokens.
    Returns a plain dict so the shape can evolve without a schema change.
    """
    with DatabaseConnection(DB_PATH) as conn:
        counts = {
            "users"       : conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "doctors"     : conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0],
            "patients"    : conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0],
            "appointments": conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0],
        }

    return {
        "status"      : "healthy",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "counts"      : counts,
        "version"     : "1.0.0",
    }