"""Validated wire formats and answer validation shared by every deployment."""

from datetime import date
from enum import StrEnum
import math
import re
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class QuestionType(StrEnum):
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    EMAIL = "email"
    NUMBER = "number"
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    RATING = "rating"
    DATE = "date"


class Question(Model):
    id: UUID = Field(default_factory=uuid4)
    type: QuestionType = QuestionType.SHORT_TEXT
    title: Annotated[str, Field(min_length=1, max_length=240)]
    help_text: Annotated[str, Field(max_length=1000)] = ""
    required: bool = False
    options: Annotated[list[Annotated[str, Field(min_length=1, max_length=200)]], Field(max_length=30)] = []
    min_value: float | None = None
    max_value: float | None = None

    @model_validator(mode="after")
    def check_configuration(self):
        if self.type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE):
            if len(self.options) < 2 or len(set(self.options)) != len(self.options):
                raise ValueError("Choice questions need 2–30 distinct, non-empty options.")
        elif self.options:
            raise ValueError("Only choice questions can have options.")
        if self.type == QuestionType.RATING:
            self.min_value = 1 if self.min_value is None else self.min_value
            self.max_value = 5 if self.max_value is None else self.max_value
            if self.min_value != 1 or self.max_value not in (3, 4, 5, 6, 7, 8, 9, 10):
                raise ValueError("Ratings start at 1 and end at an integer from 3 to 10.")
        elif self.type != QuestionType.NUMBER and (self.min_value is not None or self.max_value is not None):
            raise ValueError("Only number and rating questions can have bounds.")
        if self.min_value is not None and self.max_value is not None and self.min_value >= self.max_value:
            raise ValueError("The minimum must be less than the maximum.")
        return self


class SurveyCreate(Model):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=4000)] = ""
    respondent_mode: Literal["anonymous", "named"] = "anonymous"
    questions: Annotated[list[Question], Field(max_length=50)] = []

    @field_validator("questions")
    @classmethod
    def unique_question_ids(cls, questions):
        if len({q.id for q in questions}) != len(questions):
            raise ValueError("Question IDs must be unique.")
        return questions


class SurveyUpdate(SurveyCreate):
    revision: Annotated[int, Field(ge=1)]


class SurveyOut(SurveyCreate):
    id: UUID
    status: Literal["draft", "published", "closed"]
    revision: int
    created_at: str
    updated_at: str
    published_at: str | None
    response_count: int = 0
    public_path: str


class SurveyPage(Model):
    items: list[SurveyOut]
    total: int
    limit: int
    offset: int


class PublicSurvey(Model):
    title: str
    description: str
    respondent_mode: Literal["anonymous", "named"]
    questions: list[Question]


class Submission(Model):
    submission_id: UUID = Field(default_factory=uuid4)
    respondent_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    answers: dict[str, Any]


class Receipt(Model):
    id: UUID
    submitted_at: str


class ResponseOut(Model):
    id: UUID
    answers: dict[str, Any]
    submitted_at: str
    respondent_name: str | None = None


class ResponsePage(Model):
    items: list[ResponseOut]
    total: int
    limit: int
    offset: int


Scope = Literal["surveys:read", "surveys:write", "responses:read", "responses:delete"]
ALL_SCOPES = {"surveys:read", "surveys:write", "responses:read", "responses:delete"}


class KeyCreate(Model):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    scopes: Annotated[list[Scope], Field(min_length=1, max_length=4)] = ["surveys:read"]

    @field_validator("scopes")
    @classmethod
    def distinct_scopes(cls, scopes):
        if len(set(scopes)) != len(scopes):
            raise ValueError("Scopes must be unique.")
        return scopes


class KeyOut(Model):
    id: UUID
    name: str
    prefix: str
    scopes: list[Scope]
    created_at: str


class KeyCreated(KeyOut):
    key: str


class QuestionSummary(Model):
    question_id: UUID
    title: str
    type: QuestionType
    answered: int
    average: float | None = None
    counts: dict[str, int] = {}


class ResultsSummary(Model):
    total: int
    questions: list[QuestionSummary]


class AnswerError(ValueError):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("One or more answers are invalid.")


def validate_answers(survey: SurveyCreate, submission: Submission) -> dict[str, Any]:
    errors: dict[str, str] = {}
    cleaned: dict[str, Any] = {}
    known = {str(q.id) for q in survey.questions}
    if set(submission.answers) - known:
        errors["answers"] = "Answers contain an unknown question ID."
    if survey.respondent_mode == "anonymous" and submission.respondent_name is not None:
        errors["respondent_name"] = "Anonymous surveys do not accept respondent names."
    if survey.respondent_mode == "named" and not submission.respondent_name:
        errors["respondent_name"] = "Please enter your name."
    for question in survey.questions:
        key = str(question.id)
        value = submission.answers.get(key)
        if isinstance(value, str):
            value = value.strip()
        if value is None or value == "" or value == []:
            if question.required:
                errors[key] = "This question is required."
            continue
        kind = question.type
        error = None
        if kind in (QuestionType.SHORT_TEXT, QuestionType.LONG_TEXT, QuestionType.EMAIL, QuestionType.DATE):
            max_length = 8000 if kind == QuestionType.LONG_TEXT else 1000
            if not isinstance(value, str) or len(value) > max_length:
                error = f"Enter text of at most {max_length} characters."
            elif kind == QuestionType.EMAIL and (len(value) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)):
                error = "Enter a valid email address."
            elif kind == QuestionType.DATE:
                try:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                        raise ValueError()
                    date.fromisoformat(value)
                except ValueError:
                    error = "Enter a valid date in YYYY-MM-DD format."
        elif kind in (QuestionType.NUMBER, QuestionType.RATING):
            try:
                finite_number = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
            except OverflowError:
                finite_number = False
            if not finite_number:
                error = "Enter a finite number."
            elif kind == QuestionType.RATING and value != int(value):
                error = "Choose a whole-number rating."
            elif question.min_value is not None and value < question.min_value:
                error = f"The minimum is {question.min_value:g}."
            elif question.max_value is not None and value > question.max_value:
                error = f"The maximum is {question.max_value:g}."
        elif kind == QuestionType.SINGLE_CHOICE:
            if not isinstance(value, str) or value not in question.options:
                error = "Choose one of the listed options."
        elif kind == QuestionType.MULTIPLE_CHOICE:
            if not isinstance(value, list) or any(not isinstance(v, str) or v not in question.options for v in value):
                error = "Choose from the listed options."
            elif len(value) != len(set(value)):
                error = "Choose each option only once."
        if error:
            errors[key] = error
        else:
            cleaned[key] = value
    if errors:
        raise AnswerError(errors)
    return cleaned
