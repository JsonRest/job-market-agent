"""
Track 3 – Philippine Tech Job Market NL Query Agent
Dataset:  Philippine Tech Job Market (companies + job_postings)
Use case: Querying Philippine tech job market data by skills, salary, and company

Requirements: pip install google-adk google-cloud-alloydb-connector[asyncpg] python-dotenv
Python: 3.10+

Run locally:  adk run job_market_agent
Run with UI:  adk web
Deploy:       adk deploy cloud_run ...
"""

import os
import asyncio
from dotenv import load_dotenv
import asyncpg
from google.cloud.alloydb.connector import AsyncConnector, IPTypes
from google.adk.agents import LlmAgent

from decimal import Decimal


def _json_safe(val):
    """Convert asyncpg types that are not JSON serializable to native Python types."""
    if isinstance(val, Decimal):
        return int(val) if val == val.to_integral_value() else float(val)
    return val

# ── Connection config ─────────────────────────────────────────────────────────
PROJECT      = os.environ["GOOGLE_CLOUD_PROJECT"]
REGION       = os.getenv("ALLOYDB_REGION", "us-central1")
CLUSTER      = os.getenv("ALLOYDB_CLUSTER", "job-market-cluster")
INSTANCE     = os.getenv("ALLOYDB_INSTANCE", "job-market-instance")
DB_USER      = os.getenv("ALLOYDB_USER", "postgres")
DB_PASS      = os.environ["ALLOYDB_PASSWORD"]
DB_NAME      = os.getenv("ALLOYDB_DB", "job_market_db")
MODEL        = os.getenv("MODEL", "gemini-2.5-flash-lite")

ALLOYDB_IP_TYPE = os.getenv("ALLOYDB_IP_TYPE", "private").lower()
_ip_type = IPTypes.PUBLIC if ALLOYDB_IP_TYPE == "public" else IPTypes.PRIVATE
    f"projects/{PROJECT}/locations/{REGION}"
    f"/clusters/{CLUSTER}/instances/{INSTANCE}"
)

# Connector singleton – reused across calls within a container instance
_connector: AsyncConnector | None = None


async def _get_conn() -> asyncpg.Connection:
    """Return a fresh AlloyDB connection using the Auth Proxy connector."""
    global _connector
    if _connector is None:
        _connector = AsyncConnector()
    return await _connector.connect(
        INSTANCE_URI,
        "asyncpg",
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        ip_type=_ip_type,
    )


# ── Database schema context (injected into the agent's system prompt) ─────────
DB_SCHEMA_CONTEXT = """
Database: job_market_db (AlloyDB for PostgreSQL)
AI Extensions enabled:
  - google_ml_integration  →  AlloyDB AI (Vertex AI embeddings from SQL via embedding() function)
  - vector (pgvector)      →  semantic similarity search on job_embeddings

Tables:

  companies (
      id             SERIAL PRIMARY KEY,
      name           VARCHAR(200),
      industry       VARCHAR(100),
      company_size   VARCHAR(50),   -- 'startup' | 'sme' | 'enterprise'
      headquarters   VARCHAR(100),
      website        VARCHAR(200),
      founded_year   INTEGER
  )

  job_postings (
      id                   SERIAL PRIMARY KEY,
      company_id           INTEGER → companies.id,
      title                VARCHAR(200),
      department           VARCHAR(100),
      skills_required      TEXT[],          -- PostgreSQL array
      experience_years_min INTEGER,
      experience_years_max INTEGER,
      salary_min           INTEGER,         -- Philippine Peso (PHP)
      salary_max           INTEGER,         -- Philippine Peso (PHP)
      location             VARCHAR(100),
      remote_type          VARCHAR(50),     -- 'onsite' | 'remote' | 'hybrid'
      posted_date          DATE,
      is_active            BOOLEAN,
      description          TEXT
  )

  job_embeddings (
      job_id    INTEGER PK → job_postings.id,
      embedding vector(768)                 -- AlloyDB AI generated embeddings
  )

Key rules:
  - Filter skills with: 'Python' = ANY(skills_required)
  - Use ILIKE for location searches: location ILIKE '%Metro Manila%' or location ILIKE '%Taguig%'
  - "Metro Manila" queries should use: location ILIKE '%Manila%' OR location ILIKE '%Taguig%' OR location ILIKE '%Makati%' OR location ILIKE '%Quezon City%' OR location ILIKE '%Mandaluyong%' OR location ILIKE '%Pasig%'
  - Always include WHERE is_active = true unless the user asks about inactive roles
  - salary_min / salary_max are in Philippine Peso (PHP / ₱)
  - Add LIMIT 20 for row-returning SELECT queries; no limit for COUNT/aggregate queries
  - Only use read-only SELECT statements — never UPDATE, DELETE, or INSERT
"""


# ── Tool: execute SQL against AlloyDB ────────────────────────────────────────
async def execute_sql(sql: str) -> dict:
    """
    Execute a read-only SQL SELECT query against the AlloyDB job market database
    and return the results.

    Args:
        sql: A valid PostgreSQL SELECT statement to run against job_market_db.

    Returns:
        dict with keys:
          - success (bool)
          - row_count (int)
          - rows (list[dict])  – each dict is one database row
          - sql (str)          – the query that was executed
          - error (str)        – only present on failure
    """
    conn = await _get_conn()
    try:
        records = await conn.fetch(sql)
        rows = [{k: _json_safe(v) for k, v in dict(r).items()} for r in records]
        return {
            "success": True,
            "row_count": len(rows),
            "rows": rows,
            "sql": sql,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "sql": sql,
        }
    finally:
        await conn.close()


# ── Agent instruction ─────────────────────────────────────────────────────────
INSTRUCTION = f"""
You are a Job Market Data Analyst specializing in the Philippine tech sector.
You have access to an AlloyDB database with real-world-style job postings and company data.
AlloyDB AI (google_ml_integration + pgvector) is enabled on this database.

{DB_SCHEMA_CONTEXT}

Workflow for every user question:
1. Understand the user's intent (jobs, salaries, skills, companies, counts, trends).
2. Write a correct, safe, read-only SELECT query that answers the question.
3. Call execute_sql with the query.
4. If execute_sql returns an error, inspect it, correct the SQL, and retry once.
5. Present results in a clean, readable format with brief analytical insights.

Always give context around numbers — for example:
  - Compare salaries to the dataset average
  - Highlight which skills are most in demand
  - Note whether a job is remote-friendly

Sample questions you can handle:
  - "What Python jobs are available in Metro Manila?"
  - "Which company pays the highest average salary?"
  - "Show me remote jobs requiring React skills"
  - "How many jobs require 5+ years of experience?"
  - "List the top 5 most in-demand skills"
"""

# ── Root agent (discovered by ADK via this variable name) ────────────────────
root_agent = LlmAgent(
    name="ph_job_market_agent",
    model=MODEL,
    description=(
        "Natural-language query interface for the Philippine Tech Job Market database "
        "on AlloyDB. Ask about salaries, skills, companies, job counts, and more."
    ),
    instruction=INSTRUCTION,
    tools=[execute_sql],
)
