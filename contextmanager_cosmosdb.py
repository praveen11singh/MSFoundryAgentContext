import os
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition

from cosmosmemory import LongTermMemoryStore, MultiChatIndex
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 0. CLIENT SETUP
# ---------------------------------------------------------------------------

FOUNDRY_PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
FOUNDRY_MODEL_DEPLOYMENT = os.environ["FOUNDRY_CHAT_MODEL_DEPLOYMENT_NAME"]
FOUNDRY_AGENT_NAME = os.environ.get("AZURE_FOUNDRY_AGENT_ID", "context-demo-agent")

_credential = DefaultAzureCredential()
project_client = AIProjectClient(
    endpoint=FOUNDRY_PROJECT_ENDPOINT,
    credential=_credential,
)
openai_client = project_client.get_openai_client()


def create_agent_if_missing(name: str = FOUNDRY_AGENT_NAME,
                             model: str = FOUNDRY_MODEL_DEPLOYMENT,
                             instructions: str = "You are a helpful assistant.") -> str:
    """Create (or reuse) an agent definition. In real apps, do this once at
    deploy time, not on every run. Returns the agent's NAME, which is what
    the Responses API references (not a numeric/opaque id)."""
    try:
        existing = project_client.agents.get_version(agent_name=name, agent_version="latest")
        if existing:
            return name
    except Exception:
        pass  # not found -> create it

    project_client.agents.create_version(
        agent_name=name,
        definition=PromptAgentDefinition(
            model=model,
            instructions=instructions,
        ),
    )
    return name


# ---------------------------------------------------------------------------
# 1 & 2. CONVERSATIONAL CONTEXT + FOLLOW-UP CONTEXT  (native: Foundry conversations)
# ---------------------------------------------------------------------------

def create_conversation() -> str:
    """Starts a new, empty conversation and returns its id."""
    conversation = openai_client.conversations.create()
    return conversation.id


def send_message(conversation_id: str, agent_name: str, user_text: str) -> str:
    """Send one user message into an existing conversation and return the
    agent's reply. This single call is what gives you conversational +
    follow-up context."""
    openai_client.conversations.items.create(
        conversation_id=conversation_id,
        items=[{"type": "message", "role": "user", "content": user_text}],
    )

    response = openai_client.responses.create(
        conversation=conversation_id,
        extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
        input="",
    )

    return response.output_text


# ---------------------------------------------------------------------------
# 3. LONG-TERM CONTEXT  (persisted user memory injected into conversations)
# ---------------------------------------------------------------------------
long_term_store = LongTermMemoryStore()


def start_conversation_with_long_term_context(user_id: str) -> str:
    """Creates a new conversation and seeds it with whatever we durably know
    about this user, so day 30's conversation can reference facts from day 1."""
    conversation_id = create_conversation()

    memory = long_term_store.get_memory(user_id)
    if memory:
        openai_client.conversations.items.create(
            conversation_id=conversation_id,
            items=[{
                "type": "message",
                "role": "user",
                "content": (
                    "[BACKGROUND CONTEXT -- durable facts about this user from "
                    f"prior sessions, not a message they just sent]\n{memory}"
                ),
            }],
        )
    return conversation_id


def summarize_conversation_into_long_term_memory(conversation_id: str, user_id: str, agent_name: str) -> None:
    """Call this at the end of a session (or periodically) to compress a
    conversation's content into durable long-term memory."""
    items = list(openai_client.conversations.items.list(conversation_id=conversation_id))
    transcript_lines = []
    for item in items:
        if getattr(item, "type", None) == "message":
            role = getattr(item, "role", "unknown")
            content = getattr(item, "content", "")
            transcript_lines.append(f"{role}: {content}")
    transcript = "\n".join(transcript_lines)

    summary_conversation_id = create_conversation()
    summary = send_message(
        summary_conversation_id,
        agent_name,
        "Summarize the durable facts worth remembering about the user from this "
        "transcript in 3-5 bullet points (preferences, goals, ongoing context). "
        f"Ignore small talk.\n\nTRANSCRIPT:\n{transcript}",
    )
    long_term_store.set_memory(user_id, summary)


# ---------------------------------------------------------------------------
# 4. MULTI-CHAT CONTEXT  (many conversations per user, like a sidebar)
# ---------------------------------------------------------------------------
multi_chat_index = MultiChatIndex()


# ---------------------------------------------------------------------------
# PUTTING IT ALL TOGETHER -- end-to-end example
# ---------------------------------------------------------------------------

def demo():
    agent_name = create_agent_if_missing()
    user_id = "user_42"

    # --- Multi-chat: start TWO separate conversations for the same user ---
    conv_a = start_conversation_with_long_term_context(user_id)
    multi_chat_index.create_chat(user_id, "Trip planning", conv_a)

    conv_b = start_conversation_with_long_term_context(user_id)
    multi_chat_index.create_chat(user_id, "Resume help", conv_b)

    # --- Conversational + follow-up context inside "Trip planning" chat ---
    print(send_message(conv_a, agent_name, "I'm planning a trip to Japan in October."))
    print(send_message(conv_a, agent_name, "What should I pack for that?"))  # "that" resolved via conversation history

    # --- Switch to the OTHER chat -- completely separate context ---
    print(send_message(conv_b, agent_name, "Can you review my resume bullet points?"))

    # --- End of session: compress chat A into long-term memory ---
    summarize_conversation_into_long_term_memory(conv_a, user_id, agent_name)

    # --- Days later: new conversation, but long-term memory gets re-injected ---
    new_conv = start_conversation_with_long_term_context(user_id)
    print(send_message(new_conv, agent_name, "Hey, remind me what we were planning?"))


if __name__ == "__main__":
    demo()
