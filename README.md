# MSFoundryContext

This repository contains a small Python example for managing conversational context with Azure AI Foundry / Azure OpenAI-style conversations.

## What it contains

The project demonstrates several context patterns:

- conversational context using Foundry conversations
- follow-up context without re-sending full history
- long-term memory persisted to a local JSON store
- multi-chat indexing for multiple conversations per user

## Files

- `contextmanager.py` – main implementation for creating conversations, sending messages, and persisting memory/chat state
- `conversational_context.py` – example usage for conversational context
- `followup_context.py` – example usage for follow-up context
- `longterm_context.py` – example usage for long-term memory
- `multichat_context.py` – example usage for multi-chat handling
- `user_memory_store.json` – persisted long-term memory data
- `user_chats_index.json` – persisted chat index data

## Prerequisites

Before running the examples, make sure you have:

- Python 3.9+
- the Azure AI/identity packages installed
- environment variables configured for your Azure Foundry project

Required environment variables include:

- `FOUNDRY_PROJECT_ENDPOINT`
- `FOUNDRY_CHAT_MODEL_DEPLOYMENT_NAME`
- optionally `AZURE_FOUNDRY_AGENT_ID`

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

   ```bash
   pip install azure-identity azure-ai-projects python-dotenv
   ```

3. Create a `.env` file with your Azure Foundry configuration.
4. Run any of the example scripts, for example:

   ```bash
   python conversational_context.py
   ```

## Notes

The current implementation uses local JSON files for persistence. In a production system, you would typically replace these stores with a database or other durable service.
