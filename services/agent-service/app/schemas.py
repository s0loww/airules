"""Wire contract for POST /agent/turn.

These models mirror exactly what the 1C client (CommonModule.AsistenteIAServer) sends and
parses. Messages follow the OpenAI chat shape so the service stays a thin adapter:

  request  : {"context": {"lang","user","today"},
              "messages":[{"role","content"}                                  -- user/assistant text
                          | {"role":"assistant","content","tool_calls":[...]} -- model asked for tools
                          | {"role":"tool","tool_call_id","content"}],        -- 1C-executed result (JSON string)
              "tools":[{"name","description","risk","parameters"}]}
  response : {"type":"message","text": str, "citations":[str], "new_topic": bool}
           | {"type":"tool_calls","calls":[{"id","name","arguments":{}}], "new_topic": bool}

A request whose LAST message is a "tool" result is a resume POST of an in-flight agent turn:
the service answers it without topic classification or history trimming.

1C reads `text` and each `citations[]` item through String(), so citations MUST be strings.
"""

from __future__ import annotations

from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict, Field


class TurnContext(BaseModel):
    # Tolerate extra context keys (empresa, etc.) the client may add later.
    model_config = ConfigDict(extra="allow")
    lang: str = "es"
    user: str = ""
    # The client's current date (ISO YYYY-MM-DD). Lets the model resolve relative periods
    # ("last month", "this year") into concrete date_from/date_to using the user's clock.
    today: str = ""


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class TurnMessage(BaseModel):
    role: str = "user"
    content: str = ""
    # Set on an assistant message when the model asked for tools (echoed back by 1C so the
    # model sees its own call on the next round trip of the loop).
    tool_calls: List[ToolCall] = Field(default_factory=list)
    # Set on a "tool" message: which call this result answers.
    tool_call_id: str = ""


class TurnTool(BaseModel):
    name: str
    description: str = ""
    risk: str = "read"
    # JSON Schema for the tool arguments, sent by the 1C client. Empty -> free-form object.
    parameters: dict[str, Any] = Field(default_factory=dict)


class TurnRequest(BaseModel):
    context: TurnContext = Field(default_factory=TurnContext)
    messages: List[TurnMessage] = Field(default_factory=list)
    tools: List[TurnTool] = Field(default_factory=list)


class MessageResponse(BaseModel):
    type: Literal["message"] = "message"
    text: str
    citations: List[str] = Field(default_factory=list)
    # True when the latest user message starts a new topic unrelated to the earlier conversation.
    # The 1C client uses this to branch the turn into a fresh chat.
    new_topic: bool = False


class ToolCallsResponse(BaseModel):
    type: Literal["tool_calls"] = "tool_calls"
    calls: List[ToolCall]
    # Same meaning as on MessageResponse — the first response of a turn may already be tool
    # calls, and the 1C client still needs the branching decision.
    new_topic: bool = False
