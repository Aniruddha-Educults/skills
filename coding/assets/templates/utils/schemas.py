from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from typing_extensions import TypedDict


class ChatMessage(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: str


class User(BaseModel):
    gid: str = Field(alias="user_id")
    email: str = Field(alias="user_email", min_length=1)
    region: str | None = Field(default=None, alias="geographicregion")
    ad_groups: list[str] = Field(default_factory=list, alias="user_ad_groups")
    partial_connector_groups: list[str] = Field(default_factory=list, alias="connector_group")
    country: str | None = Field(default=None, alias="user_country")

    @property
    def connector_groups(self) -> list[str]:
        return [*self.partial_connector_groups, "All", self.email]


class PromptDetails(BaseModel):
    id: int = Field(alias="prompt_id")
    text: str | None = Field(default=None, alias="prompt")
    parent_id: int | None = Field(default=None, alias="parent_prompt_id")


class DatasourceDetails(BaseModel):
    id: str | None = Field(default=None, alias="data_source_id")
    owner: str = Field(default="", alias="datasource_owner")
    documents: list[str] = Field(default_factory=list, alias="source_files")
    search_index: str | None = None
    score_threshold: float | None = None
    max_context_tokens: int | None = Field(default=None, gt=0)


class ChatDetails(BaseModel):
    chat_history: list[ChatMessage] = Field(default_factory=list)
    user_message: str = Field(min_length=1)
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), alias="prompt_run_id", min_length=1)

    @property
    def full_chat(self) -> list[ChatMessage]:
        return [
            *[ChatMessage(role=message["role"], content=message["content"]) for message in self.chat_history],
            ChatMessage(role="user", content=self.user_message),
        ]


class FinalAnswerResponse(BaseModel):
    answer: str
    follow_up_questions: list[str] = Field(default_factory=list, max_length=3)
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)


class ChatRequest(BaseModel):
    user: User
    prompt: PromptDetails
    datasource: DatasourceDetails
    chat: ChatDetails
    app_id: int
    x_project_origin: str | None = None

    @model_validator(mode="before")
    @classmethod
    def transform_flat_to_nested(cls, data: object) -> object:
        if not isinstance(data, dict) or any(key in data for key in ("user", "datasource", "chat")):
            return data
        history = data.get("chat_history")
        chat = {
            "chat_history": [] if history is None else history,
            "user_message": data.get("user_message"),
        }
        if data.get("prompt_run_id") is not None:
            chat["prompt_run_id"] = data["prompt_run_id"]
        return {
            "user": {
                "user_id": data.get("user_id"),
                "user_email": data.get("user_email"),
                "geographicregion": data.get("geographicregion"),
                "user_ad_groups": data.get("user_ad_groups", []),
                "connector_group": data.get("connector_group", []),
                "user_country": data.get("user_country"),
            },
            "prompt": {
                "prompt_id": data.get("prompt_id"),
                "prompt": data.get("prompt"),
                "parent_prompt_id": data.get("parent_prompt_id"),
            },
            "datasource": {
                "data_source_id": data.get("data_source_id"),
                "datasource_owner": data.get("datasource_owner", ""),
                "source_files": data.get("source_files", []),
                "search_index": data.get("search_index"),
                "score_threshold": data.get("score_threshold"),
                "max_context_tokens": data.get("max_context_tokens"),
            },
            "chat": chat,
            "app_id": data.get("app_id"),
            "x_project_origin": data.get("x_project_origin"),
        }
