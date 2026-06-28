import os
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
AGENT_ID = os.environ["AZURE_FOUNDRY_AGENT_ID"]


def main() -> None:
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project,
        project.get_openai_client() as openai_client,
    ):
        # Look up the agent so we have its `name` (responses.create() references
        # agents by name, not by ID, via agent_reference).
        agent = project.agents.get(AGENT_ID)
        print(f"Using agent: {agent.name} (id: {agent.id})")

        # A conversation object is what holds multi-turn context now —
        # it replaces the old "thread".
        conversation = openai_client.conversations.create(
            items=[
                {
                    "type": "message",
                    "role": "user",
                    "content": "My name is Alice. I love Python.",
                }
            ],
        )
        print(f"Created conversation (id: {conversation.id})")

        response = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
        )
        print(f"[assistant]: {response.output_text}")

        # Ask a follow-up — the agent retains context because we're
        # reusing the same conversation.
        openai_client.conversations.items.create(
            conversation_id=conversation.id,
            items=[
                {
                    "type": "message",
                    "role": "user",
                    "content": "What language did I say I love?",
                }
            ],
        )

        response = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
        )
        print(f"[assistant]: {response.output_text}")

        # Optional: list every item (message) in the conversation so far.
        print("\n--- Full conversation ---")
        for item in openai_client.conversations.items.list(conversation_id=conversation.id):
            if item.type == "message":
                text = "".join(
                    part.text for part in item.content if getattr(part, "type", None) == "input_text" or hasattr(part, "text")
                )
                print(f"[{item.role}]: {text}")

        # Clean up the conversation when done.
        openai_client.conversations.delete(conversation_id=conversation.id)
        print("\nConversation deleted")


if __name__ == "__main__":
    main()