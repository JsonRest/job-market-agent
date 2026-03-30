#!/usr/bin/env python3
"""
setup_db.py – One-time AlloyDB schema creation and sample data loading.

Run ONCE after creating the AlloyDB cluster and instance:
    python setup_db.py

Prerequisites:
    - AlloyDB cluster + instance already created (see README.md)
    - Application Default Credentials active: gcloud auth application-default login
    - .env file populated with all ALLOYDB_* and GOOGLE_CLOUD_PROJECT vars
"""

import asyncio
import os
from dotenv import load_dotenv
import asyncpg
from google.cloud.alloydb.connector import AsyncConnector, IPTypes

load_dotenv()

PROJECT      = os.environ["GOOGLE_CLOUD_PROJECT"]
REGION       = os.getenv("ALLOYDB_REGION",   "us-central1")
CLUSTER      = os.getenv("ALLOYDB_CLUSTER",  "job-market-cluster")
INSTANCE     = os.getenv("ALLOYDB_INSTANCE", "job-market-instance")
DB_USER      = os.getenv("ALLOYDB_USER",     "postgres")
DB_PASS      = os.environ["ALLOYDB_PASSWORD"]
DB_NAME      = os.getenv("ALLOYDB_DB",       "job_market_db")

INSTANCE_URI = (
    f"projects/{PROJECT}/locations/{REGION}"
    f"/clusters/{CLUSTER}/instances/{INSTANCE}"
)

# ── DDL ───────────────────────────────────────────────────────────────────────
DDL = """
-- AlloyDB AI: natural language + embedding support
CREATE EXTENSION IF NOT EXISTS google_ml_integration;
-- pgvector: semantic similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Allow all users to call the AlloyDB AI embedding() function
GRANT EXECUTE ON FUNCTION embedding TO PUBLIC;

-- Companies directory
CREATE TABLE IF NOT EXISTS companies (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(200) NOT NULL,
    industry       VARCHAR(100),
    company_size   VARCHAR(50)  CHECK (company_size IN ('startup','sme','enterprise')),
    headquarters   VARCHAR(100),
    website        VARCHAR(200),
    founded_year   INTEGER
);

-- Job postings (custom schema – not from any lab dataset)
CREATE TABLE IF NOT EXISTS job_postings (
    id                   SERIAL PRIMARY KEY,
    company_id           INTEGER REFERENCES companies(id),
    title                VARCHAR(200) NOT NULL,
    department           VARCHAR(100),
    skills_required      TEXT[],
    experience_years_min INTEGER DEFAULT 0,
    experience_years_max INTEGER,
    salary_min           INTEGER,
    salary_max           INTEGER,
    location             VARCHAR(100),
    remote_type          VARCHAR(50) DEFAULT 'onsite'
                         CHECK (remote_type IN ('onsite','remote','hybrid')),
    posted_date          DATE    DEFAULT CURRENT_DATE,
    is_active            BOOLEAN DEFAULT TRUE,
    description          TEXT
);

-- AlloyDB AI: vector embeddings for semantic search
CREATE TABLE IF NOT EXISTS job_embeddings (
    job_id    INTEGER PRIMARY KEY REFERENCES job_postings(id) ON DELETE CASCADE,
    embedding vector(768)
);

CREATE INDEX IF NOT EXISTS job_embeddings_ivfflat
    ON job_embeddings USING ivfflat (embedding vector_l2_ops)
    WITH (lists = 50);
"""

# ── Sample data – Philippine Tech Job Market ──────────────────────────────────
COMPANIES = [
    ("Accenture Philippines",   "IT Services",          "enterprise", "Taguig, Metro Manila",      "https://accenture.com",   2001),
    ("Globe Telecom",           "Telecommunications",   "enterprise", "Taguig, Metro Manila",      "https://globe.com.ph",    1935),
    ("Sprout Solutions",        "HR Tech",              "startup",    "Mandaluyong, Metro Manila", "https://sprout.ph",       2015),
    ("Exist Software Labs",     "Software Development", "sme",        "Quezon City, Metro Manila", "https://exist.com",       1999),
    ("KMC Savills",             "Real Estate Tech",     "sme",        "Makati, Metro Manila",      "https://kmc.ph",          2009),
    ("Paylocity PH",            "FinTech",              "enterprise", "Cebu City",                 "https://paylocity.com",   2018),
    ("Trend Micro Philippines", "Cybersecurity",        "enterprise", "Taguig, Metro Manila",      "https://trendmicro.com",  1995),
    ("Seer-Tech Inc",           "AI/ML",                "startup",    "Quezon City, Metro Manila", "https://seer-tech.io",    2021),
    ("ING Bank Philippines",    "Banking/FinTech",      "enterprise", "Makati, Metro Manila",      "https://ing.com.ph",      2018),
    ("SoftwareOne Philippines", "Cloud Services",       "enterprise", "Taguig, Metro Manila",      "https://softwareone.com", 2010),
]

# (company_id, title, dept, skills[], exp_min, exp_max, sal_min, sal_max, location, remote, desc)
JOBS = [
    (1,  "Senior Python Developer",      "Engineering",          ["Python","Django","REST API","PostgreSQL","Docker"],                         3, 6, 80000, 120000, "Taguig, Metro Manila",      "hybrid",  "Build scalable backend services for enterprise clients."),
    (1,  "Data Engineer",               "Data & Analytics",     ["Python","Apache Spark","BigQuery","dbt","SQL"],                             2, 5, 70000, 100000, "Taguig, Metro Manila",      "hybrid",  "Design and maintain data pipelines for analytics."),
    (2,  "Cloud Architect",             "Infrastructure",       ["GCP","AWS","Terraform","Kubernetes","Networking"],                          5,10,120000, 180000, "Taguig, Metro Manila",      "hybrid",  "Architect cloud infrastructure for telecom services."),
    (2,  "React Native Developer",      "Mobile Engineering",   ["React Native","JavaScript","TypeScript","Redux","REST API"],                2, 5, 60000,  90000, "Taguig, Metro Manila",      "hybrid",  "Build mobile apps for Globe's customer base."),
    (3,  "Full Stack Developer",        "Product Engineering",  ["React","Node.js","PostgreSQL","TypeScript","AWS"],                          2, 4, 65000,  95000, "Mandaluyong, Metro Manila", "remote",  "Develop HR tech product features end-to-end."),
    (3,  "Machine Learning Engineer",   "AI/ML",                ["Python","TensorFlow","PyTorch","MLflow","SQL"],                             3, 6, 90000, 130000, "Mandaluyong, Metro Manila", "remote",  "Build ML models for HR analytics predictions."),
    (4,  "Java Backend Developer",      "Engineering",          ["Java","Spring Boot","Microservices","PostgreSQL","Docker"],                 3, 7, 70000, 110000, "Quezon City, Metro Manila", "onsite",  "Develop enterprise Java applications for clients."),
    (5,  "DevOps Engineer",             "Platform Engineering", ["Kubernetes","Docker","CI/CD","Terraform","GCP"],                           2, 5, 75000, 115000, "Makati, Metro Manila",      "hybrid",  "Manage cloud infrastructure and deployment pipelines."),
    (6,  "iOS Developer",               "Mobile",               ["Swift","UIKit","SwiftUI","Xcode","REST API"],                               2, 5, 65000, 100000, "Cebu City",                 "remote",  "Build iOS apps for fintech platform."),
    (7,  "Security Engineer",           "Cybersecurity",        ["Network Security","SIEM","Penetration Testing","Python","Linux"],           3, 7, 85000, 140000, "Taguig, Metro Manila",      "hybrid",  "Protect client infrastructure from threats."),
    (8,  "AI Research Engineer",        "Research",             ["Python","PyTorch","LLM","RAG","Vector Databases"],                         2, 5, 95000, 150000, "Quezon City, Metro Manila", "remote",  "Research and develop AI/LLM applications."),
    (8,  "Data Scientist",              "AI/ML",                ["Python","R","Machine Learning","Statistics","SQL","Tableau"],               2, 5, 80000, 120000, "Quezon City, Metro Manila", "remote",  "Analyze data and build predictive models."),
    (9,  "Backend Developer (Go)",      "Engineering",          ["Go","gRPC","PostgreSQL","Redis","Kubernetes"],                              3, 6, 90000, 135000, "Makati, Metro Manila",      "hybrid",  "Build high-performance financial APIs."),
    (9,  "Frontend Developer",          "Product",              ["React","TypeScript","Next.js","GraphQL","Tailwind CSS"],                    2, 5, 65000, 100000, "Makati, Metro Manila",      "remote",  "Build customer-facing banking interfaces."),
    (10, "Cloud Solutions Architect",   "Pre-Sales",            ["Azure","AWS","GCP","Solution Design","SAP"],                               5,10,130000, 200000, "Taguig, Metro Manila",      "hybrid",  "Design cloud solutions for enterprise clients."),
    (1,  "QA Automation Engineer",      "Quality Engineering",  ["Selenium","Python","Playwright","JIRA","API Testing"],                      2, 4, 55000,  80000, "Taguig, Metro Manila",      "hybrid",  "Automate test suites for enterprise software."),
    (4,  "Android Developer",           "Mobile",               ["Kotlin","Android SDK","Jetpack Compose","REST API","Firebase"],            2, 5, 60000,  95000, "Quezon City, Metro Manila", "onsite",  "Build Android apps for local clients."),
    (6,  "Product Manager",             "Product",              ["Product Strategy","Agile","SQL","Figma","Stakeholder Management"],          4, 8,100000, 160000, "Cebu City",                 "hybrid",  "Lead product strategy for fintech platform."),
    (7,  "SOC Analyst",                 "Security Operations",  ["SIEM","Threat Intelligence","Incident Response","Linux","Network Security"],1, 3, 45000,  70000, "Taguig, Metro Manila",      "onsite",  "Monitor and respond to security incidents."),
    (5,  "UX/UI Designer",              "Design",               ["Figma","User Research","Prototyping","Design Systems","CSS"],               2, 5, 55000,  85000, "Makati, Metro Manila",      "hybrid",  "Design intuitive interfaces for PropTech platform."),
]


async def main() -> None:
    print(f"Connecting to AlloyDB: {INSTANCE_URI}")
    connector = AsyncConnector()
    conn: asyncpg.Connection = await connector.connect(
        INSTANCE_URI, "asyncpg",
        user=DB_USER, password=DB_PASS, db=DB_NAME,
        ip_type=IPTypes.PUBLIC,
    )

    try:
        # ── Schema ────────────────────────────────────────────────────────────
        print("Creating schema and enabling AI extensions...")
        await conn.execute(DDL)

        # ── Truncate in reverse FK order to avoid cascade issues ────────────
        print("Clearing existing data...")
        await conn.execute("TRUNCATE job_embeddings")
        await conn.execute("TRUNCATE job_postings")
        await conn.execute("TRUNCATE companies")

        # ── Companies ─────────────────────────────────────────────────────────
        print("Loading companies...")
        for row in COMPANIES:
            await conn.execute(
                "INSERT INTO companies (name,industry,company_size,headquarters,website,founded_year) "
                "VALUES ($1,$2,$3,$4,$5,$6)",
                *row,
            )

        # ── Job postings ──────────────────────────────────────────────────────
        print("Loading job postings...")
        for row in JOBS:
            cid, title, dept, skills, emin, emax, smin, smax, loc, remote, desc = row
            await conn.execute(
                "INSERT INTO job_postings "
                "(company_id,title,department,skills_required,"
                " experience_years_min,experience_years_max,"
                " salary_min,salary_max,location,remote_type,description) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
                cid, title, dept, skills, emin, emax, smin, smax, loc, remote, desc,
            )

        # ── AlloyDB AI: generate embeddings using google_ml_integration ───────
        print("Generating job embeddings via AlloyDB AI (google_ml_integration)...")
        await conn.execute("""
            INSERT INTO job_embeddings (job_id, embedding)
            SELECT
                id,
                embedding('text-embedding-004', title || ' ' || description || ' ' || array_to_string(skills_required, ', '))
            FROM job_postings
            ON CONFLICT (job_id) DO UPDATE SET embedding = EXCLUDED.embedding
        """)

        # ── Verify ────────────────────────────────────────────────────────────
        job_count = await conn.fetchval("SELECT COUNT(*) FROM job_postings")
        emb_count = await conn.fetchval("SELECT COUNT(*) FROM job_embeddings")
        print(f"\nSetup complete!")
        print(f"  Companies loaded : {len(COMPANIES)}")
        print(f"  Job postings     : {job_count}")
        print(f"  Embeddings       : {emb_count} (AlloyDB AI)")

    finally:
        await conn.close()
    await connector.close()


if __name__ == "__main__":
    asyncio.run(main())
