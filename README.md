# Track 3 – Philippine Tech Job Market NL Query Agent

**Use case:** Querying Philippine tech job market data by skills, salary, and company using natural language.

An ADK agent backed by **AlloyDB for PostgreSQL** with AI extensions enabled. Users ask natural-language questions; the agent converts them to SQL, runs them against AlloyDB, and returns readable results.

---

## Repository Structure

```
job-market-agent/
├── job_market_agent/
│   ├── __init__.py        ← makes this a Python package (required by ADK)
│   ├── agent.py           ← root_agent definition + execute_sql tool
│   └── setup_db.py        ← one-time schema + sample data loader
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Dataset

**Philippine Tech Job Market** – a custom dataset (not from any lab).

| Table | Rows | Description |
|---|---|---|
| `companies` | 10 | PH tech companies across Metro Manila & Cebu |
| `job_postings` | 20 | Active job listings with salary (PHP) and skills |
| `job_embeddings` | 20 | AlloyDB AI–generated `text-embedding-004` vectors |

**AlloyDB AI extensions enabled:**
- `google_ml_integration` – calls Vertex AI directly from SQL via the `embedding()` function
- `vector` (pgvector) – IVFFlat index for semantic similarity search

---

## Prerequisites

All of these should already be in place from prior tracks:

- `gcloud` CLI installed and authenticated
- `uv` package manager installed
- A GCP project with billing enabled (reuse `genaiacademy-491713` or create a new one)

---

## Step 1 – Enable Required APIs

```bash
export PROJECT=genaiacademy-491713
gcloud config set project $PROJECT

gcloud services enable \
  alloydb.googleapis.com \
  aiplatform.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  servicenetworking.googleapis.com \
  compute.googleapis.com
```

---

## Step 2 – Set Up VPC Peering (required before AlloyDB)

AlloyDB uses private IP and requires a VPC peering connection to Google's Service Networking. This is a one-time setup per project.

```bash
# Allocate an IP range for Google-managed services on the default VPC
gcloud compute addresses create google-managed-services-default \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network=default \
  --project=$PROJECT

# Create the peering connection (takes ~1 minute)
gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-default \
  --network=default \
  --project=$PROJECT
```

Wait for the peering command to complete before moving on.

---

## Step 3 – Create AlloyDB Cluster & Instance

This takes approximately 10 minutes total. Run and wait for both commands to complete.

```bash
export REGION=us-central1
export ALLOYDB_PASS=your-secure-password-here

gcloud alloydb clusters create job-market-cluster \
  --region=$REGION \
  --password=$ALLOYDB_PASS \
  --project=$PROJECT

gcloud alloydb instances create job-market-instance \
  --cluster=job-market-cluster \
  --region=$REGION \
  --instance-type=PRIMARY \
  --cpu-count=2 \
  --project=$PROJECT
```

---

## Step 4 – Enable Public IP on the AlloyDB Instance

AlloyDB instances use private IP by default, which is unreachable from outside GCP. Enable public IP so the Auth Proxy can connect from your Mac.

```bash
gcloud alloydb instances update job-market-instance \
  --cluster=job-market-cluster \
  --region=us-central1 \
  --assign-inbound-public-ip=ASSIGN_IPV4 \
  --database-flags=password.enforce_complexity=on \
  --project=$PROJECT
```

This takes a couple of minutes.

---

## Step 5 – Create the Database

Use the AlloyDB Auth Proxy to open a local tunnel, then connect with `psql`.

**Download the proxy (Apple Silicon or Intel):**

```bash
# Apple Silicon (M1/M2/M3)
curl -o alloydb-auth-proxy \
  https://storage.googleapis.com/alloydb-auth-proxy/v1.13.11/alloydb-auth-proxy.darwin.arm64
chmod +x alloydb-auth-proxy

# Intel Mac
curl -o alloydb-auth-proxy \
  https://storage.googleapis.com/alloydb-auth-proxy/v1.13.11/alloydb-auth-proxy.darwin.amd64
chmod +x alloydb-auth-proxy
```

**Terminal 1 – start the proxy with `--public-ip` (keep this running):**

```bash
./alloydb-auth-proxy \
  "projects/$PROJECT/locations/$REGION/clusters/job-market-cluster/instances/job-market-instance" \
  --port=5432 \
  --public-ip
```

Wait for `ready for new connections` before proceeding.

**Terminal 2 – install the psql client if not already installed:**

```bash
brew install libpq

# libpq is keg-only and not on PATH by default — add it:
echo 'export PATH="/opt/homebrew/opt/libpq/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

**Then create the database:**

```bash
psql "host=127.0.0.1 port=5432 user=postgres" -c "CREATE DATABASE job_market_db;"
# Enter your ALLOYDB_PASS when prompted
```

You can stop the proxy after this step. `setup_db.py` uses the AlloyDB Connector library which handles auth on its own and does not need the proxy running.

---

## Step 6 – Grant AlloyDB AI Permission to Call Vertex AI

AlloyDB needs the Vertex AI User role so the `embedding()` function can call `textembedding-gecko@003` directly from SQL.

```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
ALLOYDB_SA="service-${PROJECT_NUMBER}@gcp-sa-alloydb.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:${ALLOYDB_SA}" \
  --role="roles/aiplatform.user"
```

---

## Step 7 – Clone and Configure

```bash
git clone https://github.com/JsonRest/job-market-agent.git
cd job-market-agent

cp .env.example .env
```

Edit `.env` with your values:

```
GOOGLE_CLOUD_PROJECT=genaiacademy-491713
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=True
MODEL=gemini-2.5-flash-lite

ALLOYDB_REGION=us-central1
ALLOYDB_CLUSTER=job-market-cluster
ALLOYDB_INSTANCE=job-market-instance
ALLOYDB_USER=postgres
ALLOYDB_PASSWORD=your-secure-password-here
ALLOYDB_DB=job_market_db
ALLOYDB_IP_TYPE=public
```

---

## Step 8 – Authenticate and Install

If `GOOGLE_APPLICATION_CREDENTIALS` is set from a previous project (e.g. a work account), unset it first to avoid ADC conflicts:

```bash
unset GOOGLE_APPLICATION_CREDENTIALS
gcloud auth application-default login

uv sync
```

---

## Step 9 – Load the Database (run once)

This creates all three tables, enables AlloyDB AI extensions, loads sample data, and generates vector embeddings via `embedding()`:

```bash
uv run python job_market_agent/setup_db.py
```

Expected output:

```
Connecting to AlloyDB: projects/.../instances/job-market-instance
Creating schema and enabling AI extensions...
Loading companies...
Loading job postings...
Generating job embeddings via AlloyDB AI (google_ml_integration)...

Setup complete!
  Companies loaded : 10
  Job postings     : 20
  Embeddings       : 20 (AlloyDB AI)
```

---

## Step 10 – Test Locally

Run from the repo root (not from inside `job_market_agent/`):

```bash
uv run adk web
```

Open `http://localhost:8000` in your browser. Try these queries:

- *"What Python jobs are available in Metro Manila?"*
- *"Which company pays the highest average salary?"*
- *"Show me remote jobs requiring React skills"*
- *"What are the top 5 most in-demand skills?"*

---

## Step 11 – Grant Cloud Run Build Permissions

These roles are required for `adk deploy cloud_run` to succeed. Only needed once per project.

```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:${SA}" --role="roles/storage.objectViewer"

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:${SA}" --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:${SA}" --role="roles/cloudbuild.builds.builder"
```

---

## Step 12 – Deploy to Cloud Run

Run from the repo root. Replace `your-secure-password-here` with your actual AlloyDB password.

```bash
uv run adk deploy cloud_run \
  --project=$PROJECT \
  --region=us-central1 \
  --service_name=job-market-agent \
  --with_ui \
  job_market_agent -- \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=us-central1,GOOGLE_GENAI_USE_VERTEXAI=True,MODEL=gemini-2.5-flash-lite,ALLOYDB_REGION=us-central1,ALLOYDB_CLUSTER=job-market-cluster,ALLOYDB_INSTANCE=job-market-instance,ALLOYDB_USER=postgres,ALLOYDB_PASSWORD=your-secure-password-here,ALLOYDB_DB=job_market_db,ALLOYDB_IP_TYPE=public"
```

The deploy output will end with your Cloud Run service URL — that is your submission link.

> ⚠️ Do not add `#` inline comments to the deploy command — zsh will truncate anything after `#`.

---

## Sample Natural Language Queries

| Question | What it demonstrates |
|---|---|
| "What Python jobs are available?" | Array skill filter (`'Python' = ANY(skills_required)`) |
| "Which company offers the highest average salary?" | JOIN + aggregate |
| "Show me remote jobs in Metro Manila" | Multi-condition filter |
| "How many roles require 5+ years of experience?" | COUNT + range filter |
| "List the top 5 most in-demand skills" | Array unnest + GROUP BY |
| "Compare salaries between startups and enterprise companies" | GROUP BY company_size |
| "Are there any AI/ML jobs in Cebu?" | Location + category filter |

---

## How It Satisfies All Requirements

| Requirement | Implementation |
|---|---|
| Custom dataset | Philippine Tech Job Market (not from any lab) |
| Schema created by participant | `companies`, `job_postings`, `job_embeddings` tables |
| AlloyDB AI natural language enabled | `google_ml_integration` + `vector` extensions; `embedding()` generates vectors via Vertex AI directly from SQL |
| NL → SQL conversion | ADK agent (Gemini 2.5 Flash on Vertex AI) generates SQL from the user's question |
| SQL execution against AlloyDB | `execute_sql` tool connects via AlloyDB Connector library |
| Returns relevant results | Agent formats rows with analytical context |
| Deployed to Cloud Run | `adk deploy cloud_run --with_ui` |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `setup_db.py` embedding step fails with permission error | AlloyDB SA needs `roles/aiplatform.user` — see Step 4 |
| ADC errors / wrong project credentials | `unset GOOGLE_APPLICATION_CREDENTIALS` then `gcloud auth application-default login` |
| `{"detail":"Not Found"}` at the Cloud Run URL | `--with_ui` was missing from the deploy command — redeploy |
| `adk web` shows agent not found | You ran it from inside `job_market_agent/` — move up to the repo root and use `uv run adk web` |
| AlloyDB Auth Proxy connection refused | The proxy process in Terminal 1 died; restart it before connecting with psql |
| `TimeoutError` on Cloud Run when querying | Cloud Run cannot reach AlloyDB private IP — ensure `ALLOYDB_IP_TYPE=public` is in the deploy `--set-env-vars` |

---

## Clean Up

```bash
gcloud run services delete job-market-agent --region=us-central1 --quiet
gcloud alloydb clusters delete job-market-cluster --region=us-central1 --force --quiet
```
