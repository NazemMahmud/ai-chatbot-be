from typing import Generic, TypeVar, Optional

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    message: str = ""
    data: Optional[T] = None
    statusCode: Optional[int] = None


class ValidationErrorDetail(BaseModel):
    field: str
    message: str


class ValidationErrorData(BaseModel):
    details: list[ValidationErrorDetail]
