import os
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.projects.models import (
    MemoryStoreDefaultDefinition,
    MemoryStoreDefaultOptions,
    MemorySearchPreviewTool,
    PromptAgentDefinition,
)
from dotenv import load_dotenv

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
CHAT_MODEL = os.environ["FOUNDRY_CHAT_MODEL_DEPLOYMENT_NAME"]
EMBEDDING_MODEL = os.environ["FOUNDRY_EMBEDDING_MODEL_DEPLOYMENT_NAME"]

MEMORY_STORE_NAME = "user-context-store"


def main() -> None:
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project,
    ):
        # --- Create a persistent memory store ---
        options = MemoryStoreDefaultOptions(
            chat_summary_enabled=True,
            user_profile_enabled=True,
            user_profile_details=(
                "Avoid irrelevant or sensitive data, such as age, "
                "financials, precise location, and credentials"
            ),
        )

        definition = MemoryStoreDefaultDefinition(
            chat_model=CHAT_MODEL,
            embedding_model=EMBEDDING_MODEL,
            options=options,
        )

        memory_store = project.beta.memory_stores.create(
            name=MEMORY_STORE_NAME,
            definition=definition,
            description="Memory store for context-aware agent",
        )
        print(f"Memory Store name: {memory_store.name}")

        # --- Attach memory to the agent via MemorySearchPreviewTool ---
        # `scope` segments memories per user/session. "{{$userId}}" can be used
        # to resolve scope from the request's auth identity at call time.
        scope = "user_123"

        memory_tool = MemorySearchPreviewTool(
            memory_store_name=memory_store.name,
            scope=scope,
            update_delay=1,  # demo value; use ~300 (5 min) in production
        )

        agent = project.agents.create_version(
            agent_name="context-aware-agent",
            definition=PromptAgentDefinition(
                model=CHAT_MODEL,
                instructions="You are a helpful assistant with memory.",
                tools=[memory_tool],
            ),
        )
        print(f"Agent created (name: {agent.name}, version: {agent.version})")


if __name__ == "__main__":
    main()