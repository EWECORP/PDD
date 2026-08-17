from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda value: "".join(
            word if index == 0 else word.capitalize()
            for index, word in enumerate(value.split("_"))
        ),
        populate_by_name=True,
        extra="forbid",
    )


class DirectedNeedLineWrite(ApiModel):
    branch_id: int
    article_id: int
    original_quantity: Decimal = Field(gt=0)
    target_date: date | None = None
    sla_at: datetime | None = None
    unit_code: str = Field(default="UN", min_length=1, max_length=20)


class DirectedNeedWrite(ApiModel):
    need_type: Literal["E", "C", "A"]
    business_reference: str = Field(min_length=1, max_length=120)
    supplier_id: int | None = None
    valid_from: date
    valid_to: date | None = None
    priority_score: Decimal = Decimal("0")
    owner_user: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3)
    notes: str | None = None
    lines: list[DirectedNeedLineWrite] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_business_rules(self) -> "DirectedNeedWrite":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("validTo debe ser mayor o igual que validFrom")
        pairs = [(line.branch_id, line.article_id) for line in self.lines]
        if len(pairs) != len(set(pairs)):
            raise ValueError("No se permiten líneas artículo-sucursal duplicadas")
        return self


class DirectedNeedCreate(DirectedNeedWrite):
    pass


class DirectedNeedReplace(DirectedNeedWrite):
    change_reason: str = Field(min_length=3, max_length=500)


class StateAction(ApiModel):
    reason: str = Field(min_length=3, max_length=500)


class Identity(BaseModel):
    user_id: str
    roles: frozenset[str]


class BacklogQuery(BaseModel):
    page_size: int = Field(default=50, ge=1, le=200)
    page_cursor: str | None = Field(default=None, max_length=1000)
    branch_ids: tuple[int, ...] = ()
    article_ids: tuple[int, ...] = ()
    supplier_ids: tuple[int, ...] = ()
    need_types: tuple[Literal["D", "E", "C", "A", "S"], ...] = ()
    mandatory: bool | None = None
    minimum_irq: Decimal | None = Field(default=None, ge=0, le=100)
    target_date_to: date | None = None
    freshness_statuses: tuple[Literal["CURRENT", "STALE", "INCOMPLETE"], ...] = ()
    with_alerts: bool | None = None
    search: str | None = Field(default=None, min_length=2, max_length=100)
    sort: Literal[
        "priority_desc",
        "irq_desc",
        "target_date_asc",
        "quantity_desc",
        "article_asc",
    ] = "priority_desc"


class DirectedNeedQuery(BaseModel):
    page_size: int = Field(default=50, ge=1, le=200)
    page_cursor: str | None = Field(default=None, max_length=1000)
    need_types: tuple[Literal["E", "C", "A"], ...] = ()
    statuses: tuple[Literal["DRAFT", "ACTIVE", "CLOSED", "CANCELLED", "EXPIRED"], ...] = ()
    valid_on: date | None = None
    owner_user: str | None = Field(default=None, max_length=100)
    search: str | None = Field(default=None, min_length=2, max_length=120)
