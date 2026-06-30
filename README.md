# MSFoundryContext

This repository contains Python samples that demonstrate context-aware Azure AI Foundry agents. The examples show how to manage conversation state, follow-up questions, long-term memory, and multi-turn chat experiences with Azure AI Projects.

## Solution overview

The repository includes four focused samples:

- `conversational_context.py` – creates a conversation, sends an initial prompt, and uses follow-up turns in the same conversation.
- `followup_context.py` – demonstrates how a later question can rely on earlier context in the same conversation.
- `longterm_context.py` – creates a persistent memory store and attaches memory-aware tooling to an agent.
- `multichat_context.py` – runs an interactive multi-turn chat loop against an agent.

## Prerequisites

Before running the samples, make sure you have:

- Python 3.9+
- Azure credentials available through `DefaultAzureCredential`
- An Azure AI Foundry project and deployed chat/embedding models

## Required environment variables

Create a `.env` file with the following values:

- `FOUNDRY_PROJECT_ENDPOINT`
- `AZURE_FOUNDRY_AGENT_ID`
- `FOUNDRY_CHAT_MODEL_DEPLOYMENT_NAME`
- `FOUNDRY_EMBEDDING_MODEL_DEPLOYMENT_NAME`

## Setup

1. Create and activate a virtual environment.
2. Install the required packages:

   ```bash
   pip install azure-ai-projects azure-identity python-dotenv
   ```

3. Add the environment variables to your `.env` file.
4. Run one of the sample scripts, for example:

   ```bash
   python conversational_context.py
   ```

## Notes

These samples are intended for learning and prototyping. For production use, keep secrets in a secure secret store and replace any demo memory scope or persistence approach with a more durable solution.
