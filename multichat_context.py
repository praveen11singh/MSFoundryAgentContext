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
        # Look up the agent once to get its name (agent_reference needs the
        # name, not the ID).
        agent = project.agents.get(AGENT_ID)
        agent_reference = {"name": agent.name, "type": "agent_reference"}

        # A conversation object holds context across turns, replacing the
        # old "thread".
        conversation = openai_client.conversations.create(items=[])

        print("Chat started. Type 'quit' to exit.\n")

        while True:
            user_input = input("You: ")
            if user_input.lower() == "quit":
                break

            openai_client.conversations.items.create(
                conversation_id=conversation.id,
                items=[
                    {
                        "type": "message",
                        "role": "user",
                        "content": user_input,
                    }
                ],
            )

            response = openai_client.responses.create(
                conversation=conversation.id,
                extra_body={"agent_reference": agent_reference},
            )

            print(f"Agent: {response.output_text}\n")

        openai_client.conversations.delete(conversation_id=conversation.id)


if __name__ == "__main__":
    main()