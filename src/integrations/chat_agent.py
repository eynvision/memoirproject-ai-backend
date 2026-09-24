"""
@file chat_agent.py
@description LangChain integration for the memoir chat agent. Builds a
tool-calling agent on Gemini and runs it statelessly for one chat turn: the
caller supplies the full message history, and conversation memory lives in
our own database rather than in a LangGraph checkpointer. Also converts
messages to/from the JSON stored in memoir_chat_message.
"""

from typing import List

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict
from pydantic_core import to_jsonable_python

from src.core.config import CHAT_MAX_STEPS, CHAT_TEMPERATURE
from src.integrations.llm_factory import build_chat_model


def run_agent(tools: list, system_prompt: str, messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Runs one chat turn and returns the full message list (the input messages
    followed by everything the agent added: tool calls, tool results, reply).
    """
    agent = create_agent(
        build_chat_model(CHAT_TEMPERATURE),
        tools=tools,
        system_prompt=system_prompt,
    )
    result = agent.invoke({"messages": messages}, config={"recursion_limit": CHAT_MAX_STEPS})
    return result["messages"]


def message_to_payload(message: BaseMessage) -> dict:
    """A JSON-safe dict for the jsonb column (raw messages can contain bytes)."""
    return to_jsonable_python(message_to_dict(message))


def payloads_to_messages(payloads: List[dict]) -> List[BaseMessage]:
    """Rebuilds LangChain messages from stored payloads."""
    return messages_from_dict(payloads)


def message_text(message: BaseMessage) -> str:
    """Plain text of a message; Gemini content can be a list of blocks."""
    return str(message.text)
