from fastapi import status
from typing import Generic, TypeVar, Optional

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    message: str = ""
    data: Optional[T] = None
    statusCode: Optional[int] = status.HTTP_200_OK


class ValidationErrorDetail(BaseModel):
    field: str
    message: str


class ValidationErrorData(BaseModel):
    details: list[ValidationErrorDetail]
