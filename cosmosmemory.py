import os
import time
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# CLIENT / DATABASE / CONTAINER SETUP
# ---------------------------------------------------------------------------

COSMOS_ENDPOINT = os.environ["COSMOS_ENDPOINT"]
COSMOS_DATABASE = os.environ.get("COSMOS_DATABASE", "foundry_context_db")

_cosmos_credential = DefaultAzureCredential()
_cosmos_client = CosmosClient(url=COSMOS_ENDPOINT, credential=_cosmos_credential)

# create_database_if_not_exists / create_container_if_not_exists are idempotent --
# safe to call every startup, but in production do this once at deploy time
# (via IaC/Bicep/Terraform) rather than on every process start.
_database = _cosmos_client.create_database_if_not_exists(id=COSMOS_DATABASE)

_memory_container = _database.create_container_if_not_exists(
    id="user_memory",
    partition_key=PartitionKey(path="/userId"),
)

_chats_container = _database.create_container_if_not_exists(
    id="user_chats",
    partition_key=PartitionKey(path="/userId"),
)


# ---------------------------------------------------------------------------
# 3. LONG-TERM CONTEXT  -> Cosmos-backed memory store
# ---------------------------------------------------------------------------

class LongTermMemoryStore:
    """Drop-in replacement for the JSON-file LongTermMemoryStore.
    One Cosmos item per user, in the user_memory container."""

    def __init__(self, container=_memory_container):
        self.container = container

    def get_memory(self, user_id: str) -> str:
        """Point read by (id, partition_key) -- the cheapest possible Cosmos
        operation. Returns '' if the user has no memory document yet."""
        try:
            item = self.container.read_item(item=user_id, partition_key=user_id)
            return item.get("memory", "")
        except exceptions.CosmosResourceNotFoundError:
            return ""

    def update_memory(self, user_id: str, new_fact: str) -> None:
        """Appends a durable fact about the user."""
        existing = self.get_memory(user_id)
        new_memory = (existing + "\n- " + new_fact).strip() if existing else "- " + new_fact
        self.set_memory(user_id, new_memory)

    def set_memory(self, user_id: str, full_memory: str) -> None:
        """Overwrites memory wholesale -- useful after summarizing an old
        conversation. upsert_item creates the doc if it doesn't exist yet,
        or replaces it if it does -- no need to check existence first."""
        self.container.upsert_item({
            "id": user_id,          # Cosmos requires a unique 'id' per item
            "userId": user_id,      # used as the partition key
            "memory": full_memory,
            "updatedAt": time.time(),
        })


# ---------------------------------------------------------------------------
# 4. MULTI-CHAT CONTEXT  -> Cosmos-backed chat index
# ---------------------------------------------------------------------------

class MultiChatIndex:
    """Drop-in replacement for the JSON-file MultiChatIndex.
    One Cosmos item PER CHAT (not one big array per user) in the
    user_chats container, partitioned by userId."""

    def __init__(self, container=_chats_container):
        self.container = container

    def create_chat(self, user_id: str, title: str, conversation_id: str) -> str:
        chat_id = f"chat_{int(time.time() * 1000)}"  # millisecond timestamp -> unique enough here
        self.container.upsert_item({
            "id": chat_id,
            "userId": user_id,
            "title": title,
            "conversationId": conversation_id,
            "createdAt": time.time(),
        })
        return chat_id

    def list_chats(self, user_id: str) -> list:
        """Query scoped to a single partition (userId) -- efficient, no
        cross-partition fan-out needed since we filter on the partition key."""
        query = "SELECT * FROM c WHERE c.userId = @user_id ORDER BY c.createdAt ASC"
        items = self.container.query_items(
            query=query,
            parameters=[{"name": "@user_id", "value": user_id}],
            partition_key=user_id,
        )
        return [
            {"chat_id": i["id"], "title": i["title"], "conversation_id": i["conversationId"]}
            for i in items
        ]

    def get_conversation_id(self, user_id: str, chat_id: str) -> Optional[str]:
        """Point read -- we know both the id and the partition key, so this
        is a direct lookup, not a query."""
        try:
            item = self.container.read_item(item=chat_id, partition_key=user_id)
            return item.get("conversationId")
        except exceptions.CosmosResourceNotFoundError:
            return None


# ---------------------------------------------------------------------------
# HOW TO SWITCH context_manager_v2.py OVER TO THIS
# ---------------------------------------------------------------------------
#
# In context_manager_v2.py:
#
# 1. DELETE these blocks entirely:
#      - `MEMORY_FILE = Path(...)` and the whole `class LongTermMemoryStore` (JSON version)
#      - `CHATS_FILE = Path(...)` and the whole `class MultiChatIndex` (JSON version)
#
# 2. ADD this import near the top:
#      from cosmos_store import LongTermMemoryStore, MultiChatIndex
#
# 3. Keep these two lines exactly as they are (they now construct the
#    Cosmos-backed classes instead of the JSON ones):
#      long_term_store = LongTermMemoryStore()
#      multi_chat_index = MultiChatIndex()
#
# Nothing else in context_manager_v2.py changes -- every call site
# (start_conversation_with_long_term_context, summarize_conversation_into_long_term_memory,
# demo(), etc.) uses the same method names and signatures.
#
# Also add the two new env vars wherever you set FOUNDRY_PROJECT_ENDPOINT etc.:
#      COSMOS_ENDPOINT   = https://<account-name>.documents.azure.com:443/
#      COSMOS_DATABASE   = foundry_context_db   (optional, this is the default)