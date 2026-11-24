# Passive Recon Intelligence

**Zero-Contact Passive Reconnaissance & Grounded Local AI Intelligence Platform**

Passive Recon Intelligence is an automated, strictly zero-contact OSINT and attack-surface reconnaissance platform built for cybersecurity analysts and red/blue teams. Unlike hybrid scanners that initiate direct HTTP, TLS, or port-scanning requests against target web servers, every collection module in this system queries only third-party OSINT repositories, certificate transparency logs, public recursive DNS resolvers, and domain registrar WHOIS registries—leaving zero footprint in target firewall or web server access logs.

---

## Key Features

- **100% Zero-Contact Passive Enumeration (6 Parallel Modules):**
  - **Subfinder:** Passive DNS and Certificate Transparency (CT) log subdomain discovery.
  - **Amass (Passive Mode):** ASN, netblock, and passive subdomain mapping.
  - **theHarvester:** Passive search engine and public API intelligence gathering.
  - **Waybackurls:** Historical web archive endpoint and subdomain extraction.
  - **DNS Authentication & Cloud Posture (`dns_auth`):** Public recursive resolver (`1.1.1.1` / `8.8.8.8` / `9.9.9.9`) inspection of `SPF`, `DMARC`, `MX`, `NS`, and third-party `CNAME` dependencies.
  - **Domain Governance & Lifecycle (`whois_lookup`):** Public registrar Port 43 WHOIS lookup (with async CLI fallback for slow ccTLD registries such as `.my` / MYNIC) to extract registrar, creation/expiration dates, and authoritative nameservers.
- **Deterministic Correlation Engine (Rules `C001–C005`):**
  - Automatically links subdomains, resolved IP addresses, shared hosting infrastructure (`SHARES_IP`), multi-source corroboration, and `/24` subnet groupings into a relational topology graph.
- **Multi-Source Confidence Scoring (`ConfidenceEngine`):**
  - **Authoritative DNS & WHOIS Records (`DNS_RECORD`):** Locked at **95%** authoritative confidence.
  - **Infrastructure Assets (`SUBDOMAIN` & `IP_ADDRESS`):** Dynamically scored on a **60%–100%** scale based on independent multi-tool corroboration (`1 source = 60%`, `2 sources = 80%`, `3 sources = 92%`, `4+ sources = 100%`).
- **Privacy-Preserving Local LLM + Phase 7 Grounding Gate:**
  - Synthesizes Executive and Technical intelligence briefings locally via **Ollama (`qwen2.5`)** so sensitive reconnaissance data never leaves the host machine.
  - Every generated report passes through a deterministic **Phase 7 Grounding Gate** that cross-checks LLM claims against verified database entities to prevent and flag hallucinations.
- **Interactive Dashboard & Multi-Format Reporting:**
  - BloodHound-style **Graph Explorer** with hub clustering, radial node isolation, and a live **Node Inspector**.
  - **Asset Analytics & Inventory** with composition charts, confidence distribution bars, and filterable entity tables.
  - Persistent **Execution Logs** audit trail with one-click copy.
  - Exportable **PDF**, **Microsoft Word (`.doc`)**, **CSV**, and **JSON** deliverables.

---

## System Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                        React + ReactFlow Frontend                       │
│   Target Input  │  Analytics & Tables  │  Graph Explorer  │  Exec Logs  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ REST API (FastAPI)
┌────────────────────────────────────▼────────────────────────────────────┐
│                     Asynchronous Orchestrator (jobs.py)                 │
│  ┌────────────┐ ┌─────────┐ ┌──────────────┐ ┌───────────────────────┐  │
│  │ Subfinder  │ │  Amass  │ │ theHarvester │ │      Waybackurls      │  │
│  └────────────┘ └─────────┘ └──────────────┘ └───────────────────────┘  │
│  ┌────────────────────────┐ ┌────────────────────────────────────────┐  │
│  │  dns_auth (Recursive)  │ │   whois_lookup (Port 43 + CLI Fallback)│  │
│  └────────────────────────┘ └────────────────────────────────────────┘  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────────────┐
│              PostgreSQL + Deterministic Analysis Pipeline               │
│   Raw Observations ─► Normalization ─► Correlation (C001–C005)          │
│                                     ─► ConfidenceEngine (60%–100%)      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────────────┐
│               Local AI Synthesis & Verification Layer                   │
│       Ollama (qwen2.5) ──► Phase 7 Grounding Gate ──► Final Report      │
└─────────────────────────────────────────────────────────────────────────┘
