
import os
import json
import time
from pathlib import Path
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
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
#
# A "conversation" in the v2 SDK is what a "thread" was in v1: it IS your
# conversation history. Every item you add stays in scope for every future
# response on that conversation_id, so the model resolves follow-ups
# ("what about that?") without you resending history yourself.


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
# 3. LONG-TERM CONTEXT  (custom: persisted user memory injected into conversations)
# ---------------------------------------------------------------------------
#
# Conversations don't persist meaning across DIFFERENT sessions on their own --
# each is a scoped container. For "remember this user across days/weeks", keep
# a small durable memory record per user and feed it back in whenever a new
# conversation starts, or periodically summarize an old conversation into it.
#
# Swap JSONStore for Cosmos DB / Postgres / Redis in production -- the
# interface (get_memory / update_memory) is what matters, not the storage engine.

MEMORY_FILE = Path("./user_memory_store.json")


class LongTermMemoryStore:
    """Minimal durable key-value store: user_id -> memory facts."""

    def __init__(self, path: Path = MEMORY_FILE):
        self.path = path
        if not self.path.exists():
            self.path.write_text("{}")

    def _read(self) -> dict:
        return json.loads(self.path.read_text())

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2))

    def get_memory(self, user_id: str) -> str:
        data = self._read()
        return data.get(user_id, {}).get("memory", "")

    def update_memory(self, user_id: str, new_fact: str) -> None:
        """Appends a durable fact about the user."""
        data = self._read()
        entry = data.setdefault(user_id, {"memory": "", "updated_at": None})
        existing = entry["memory"]
        entry["memory"] = (existing + "\n- " + new_fact).strip() if existing else "- " + new_fact
        entry["updated_at"] = time.time()
        self._write(data)

    def set_memory(self, user_id: str, full_memory: str) -> None:
        """Overwrites memory wholesale -- useful after summarizing an old conversation."""
        data = self._read()
        data[user_id] = {"memory": full_memory, "updated_at": time.time()}
        self._write(data)


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
# 4. MULTI-CHAT CONTEXT  (custom: many conversations per user, like a sidebar)
# ---------------------------------------------------------------------------
#
# Each "chat" the user sees in a sidebar maps 1:1 to a Foundry conversation_id.
# You keep a local index: user_id -> [ {chat_id, conversation_id, title}, ... ]
# Switching "chats" in your UI = switching which conversation_id you call
# send_message() with.

CHATS_FILE = Path("./user_chats_index.json")


class MultiChatIndex:
    """Tracks multiple named conversations ('chats') per user, each backed by
    its own Foundry conversation_id."""

    def __init__(self, path: Path = CHATS_FILE):
        self.path = path
        if not self.path.exists():
            self.path.write_text("{}")

    def _read(self) -> dict:
        return json.loads(self.path.read_text())

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2))

    def create_chat(self, user_id: str, title: str, conversation_id: str) -> str:
        data = self._read()
        user_chats = data.setdefault(user_id, [])
        chat_id = f"chat_{len(user_chats) + 1}_{int(time.time())}"
        user_chats.append({"chat_id": chat_id, "title": title, "conversation_id": conversation_id})
        self._write(data)
        return chat_id

    def list_chats(self, user_id: str) -> list:
        return self._read().get(user_id, [])

    def get_conversation_id(self, user_id: str, chat_id: str) -> Optional[str]:
        for chat in self.list_chats(user_id):
            if chat["chat_id"] == chat_id:
                return chat["conversation_id"]
        return None


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