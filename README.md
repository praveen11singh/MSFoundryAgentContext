# MSFoundryAgentContext

Python samples demonstrating **context-aware agents** built on [Azure AI Foundry](https://azure.microsoft.com/en-us/products/ai-studio) using the `azure-ai-projects` v2.x SDK. The repository covers four distinct context patterns — conversational, follow-up, long-term (Cosmos DB–backed), and multi-chat — so you can pick the right approach for your use case.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Context Patterns Explained](#context-patterns-explained)
- [SDK Version Note](#sdk-version-note)
- [Notes](#notes)

---

## Overview

Azure AI Foundry agents are stateless by default — managing conversation history and user memory across sessions is your responsibility. This repo shows you how to do that cleanly across four escalating levels of context:

| Pattern | Scope | Persistence |
|---|---|---|
| Conversational | Single session, within one conversation | In-memory (Foundry conversation) |
| Follow-up | Multi-turn within the same conversation | In-memory (Foundry conversation) |
| Long-term | Across sessions, per user | Cosmos DB |
| Multi-chat | Multiple named conversations per user | Cosmos DB |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Azure AI Foundry                       │
│  ┌─────────────┐        ┌──────────────────────────────┐ │
│  │    Agent    │◄──────►│  Conversations (v2 SDK)      │ │
│  │  (PromptAI) │        │  openai_client.responses     │ │
│  └─────────────┘        └──────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
         │                          │
         │ Long-term & Multi-chat   │
         ▼                          ▼
┌─────────────────────┐    ┌──────────────────────┐
│   Azure Cosmos DB   │    │   Local JSON Store   │
│  (cosmosmemory.py)  │    │  (contextmanager_    │
│  LongTermMemoryStore│    │   json.py)           │
│  MultiChatIndex     │    └──────────────────────┘
└─────────────────────┘
```

---

## Repository Structure

```
MSFoundryAgentContext/
├── conversational_context.py    # Pattern 1 & 2: single-session multi-turn chat
├── followup_context.py          # Pattern 2: follow-up question resolution
├── longterm_context.py          # Pattern 3: cross-session user memory (JSON backend)
├── multichat_context.py         # Pattern 4: named sidebar chats per user
├── contextmanager_cosmosdb.py   # All 4 patterns combined, Cosmos DB backend
├── contextmanager_json.py       # All 4 patterns combined, JSON file backend
├── cosmosmemory.py              # LongTermMemoryStore + MultiChatIndex (Cosmos DB)
├── .gitignore
└── README.md
```

### Key files at a glance

**`conversational_context.py`** — Creates a Foundry conversation, sends an initial prompt, and continues with follow-up turns in the same thread.

**`followup_context.py`** — Shows how a later question (e.g. "What about that?") is resolved correctly because the full conversation history is in scope.

**`longterm_context.py`** — Creates a persistent per-user memory store and injects it into every new conversation so facts learned in session 1 are available in session 30.

**`multichat_context.py`** — Manages multiple named conversations per user (like a chat sidebar), each with its own isolated context.

**`contextmanager_cosmosdb.py`** — Production-oriented version combining all four patterns, backed by Azure Cosmos DB for durable storage.

**`contextmanager_json.py`** — Development/local version of the same patterns, using JSON files instead of Cosmos DB.

**`cosmosmemory.py`** — `LongTermMemoryStore` and `MultiChatIndex` classes that abstract Cosmos DB operations (partitioned by `userId`).

---

## Prerequisites

- Python 3.9 or higher
- An [Azure AI Foundry](https://ai.azure.com) project with at least one deployed chat model and one embedding model
- Azure CLI installed and authenticated (`az login`) — used by `DefaultAzureCredential`
- (Optional, for Cosmos DB samples) An Azure Cosmos DB account

---

## Installation

```bash
# Clone the repository
git clone https://github.com/praveen11singh/MSFoundryAgentContext.git
cd MSFoundryAgentContext

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate      # macOS/Linux
.venv\Scripts\activate         # Windows

# Install dependencies
pip install azure-ai-projects azure-identity python-dotenv
```

For Cosmos DB–backed samples, also install:

```bash
pip install azure-cosmos
```

---

## Configuration

Create a `.env` file in the project root:

```env
# Required for all samples
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
AZURE_FOUNDRY_AGENT_ID=your-agent-name-or-id
FOUNDRY_CHAT_MODEL_DEPLOYMENT_NAME=gpt-4o-mini        # or your deployment name
FOUNDRY_EMBEDDING_MODEL_DEPLOYMENT_NAME=text-embedding-3-small

# Required only for Cosmos DB samples (contextmanager_cosmosdb.py, cosmosmemory.py)
COSMOS_ENDPOINT=https://<account>.documents.azure.com:443/
COSMOS_DATABASE=foundry-agent-db
COSMOS_CONTAINER=agent-context
```

> **Tip:** The `FOUNDRY_PROJECT_ENDPOINT` is found in your Foundry project's **Overview** tab under *Project details*.

---

## Usage

Run any sample directly:

```bash
# Basic conversational + follow-up context
python conversational_context.py

# Follow-up question resolution demo
python followup_context.py

# Long-term memory across sessions (JSON backend)
python longterm_context.py

# Multi-chat sidebar demo
python multichat_context.py

# Full demo — all 4 patterns, Cosmos DB backend
python contextmanager_cosmosdb.py

# Full demo — all 4 patterns, local JSON backend
python contextmanager_json.py
```

---

## Context Patterns Explained

### 1 & 2 — Conversational & Follow-up Context

Foundry's `conversation` object (v2 SDK) is the direct equivalent of a *thread* in v1. Every message you add stays in scope for every future `responses.create` call on that `conversation_id`, so the model can resolve follow-up references ("what about that?") without you manually resending history.

```python
conversation_id = openai_client.conversations.create().id
reply = send_message(conversation_id, agent_name, "I'm planning a trip to Japan.")
reply = send_message(conversation_id, agent_name, "What should I pack for that?")  # "that" resolves correctly
```

### 3 — Long-term Context

Conversations don't automatically persist meaning across separate sessions. `LongTermMemoryStore` solves this: at the end of a session, the conversation transcript is summarised into 3-5 bullet points and written to Cosmos DB (keyed by `userId`). When the user returns, those bullets are injected into the new conversation as a background context message before any user turn.

```python
# End of session — compress to memory
summarize_conversation_into_long_term_memory(conversation_id, user_id, agent_name)

# Next session — memory is automatically re-injected
new_conv = start_conversation_with_long_term_context(user_id)
```

### 4 — Multi-chat Context

`MultiChatIndex` maps human-readable chat names (e.g. `"Trip planning"`, `"Resume help"`) to Foundry `conversation_id`s, stored in Cosmos DB partitioned by `userId`. Each named chat maintains completely independent context — switching chats is equivalent to switching browser tabs.

```python
conv_a = start_conversation_with_long_term_context(user_id)
multi_chat_index.create_chat(user_id, "Trip planning", conv_a)

conv_b = start_conversation_with_long_term_context(user_id)
multi_chat_index.create_chat(user_id, "Resume help", conv_b)
```

---

## SDK Version Note

This repo targets **`azure-ai-projects` v2.x**, which has a significantly different API surface from v1.x:

| Concept | v1.x (old) | v2.x (this repo) |
|---|---|---|
| Create agent | `project_client.agents.create_agent()` | `project_client.agents.create_version()` with `PromptAgentDefinition` |
| Thread / conversation | `.threads.create()` | `openai_client.conversations.create()` |
| Send message & get reply | `.runs.create_and_process()` + `.messages.list()` | `openai_client.responses.create(conversation=...)` |

Check your installed version before running:

```bash
pip show azure-ai-projects
```

---

## Notes

- These samples are intended for **learning and prototyping**. Before using in production, store all secrets in Azure Key Vault rather than `.env` files.
- The JSON-based context manager (`contextmanager_json.py`) writes to local files and is not suitable for multi-user or distributed deployments.
- For production, replace the in-memory or JSON memory store with the Cosmos DB–backed implementation (`contextmanager_cosmosdb.py`).
- Agent creation (`create_agent_if_missing`) is idempotent but should be done **once at deploy time**, not on every run, to avoid unnecessary API calls.

---

## License

This project is provided as-is for demonstration purposes. See [LICENSE](LICENSE) if present, or treat as MIT unless otherwise stated.
