import os
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
AGENT_NAME = os.environ["AZURE_FOUNDRY_AGENT_ID"]


def main() -> None:
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project,
        project.get_openai_client() as openai_client,
    ):
        agent_reference = {"name": AGENT_NAME, "type": "agent_reference"}

        # A conversation object holds multi-turn context for agent calls.
        conversation = openai_client.conversations.create(
            items=[
                {
                    "type": "message",
                    "role": "user",
                    "content": "What is the capital of France?",
                }
            ],
        )
        print(f"Created conversation (id: {conversation.id})")

        # First turn
        response = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent_reference": agent_reference},
        )
        print("Response 1:", response.output_text)

        # Follow-up: add the next user message to the same conversation,
        # then call responses.create() again referencing that conversation.
        openai_client.conversations.items.create(
            conversation_id=conversation.id,
            items=[
                {
                    "type": "message",
                    "role": "user",
                    "content": "What is the population of that city?",
                }
            ],
        )

        follow_up = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent_reference": agent_reference},
        )
        print("Response 2:", follow_up.output_text)

        # Clean up
        openai_client.conversations.delete(conversation_id=conversation.id)
        print("Conversation deleted")


if __name__ == "__main__":
    main()