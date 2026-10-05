"""Authentication schemas for JWT tokens and user management"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class Token(BaseModel):
    """JWT token response"""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """JWT token payload structure"""

    sub: str  # User ID
    exp: datetime
    iat: datetime
    type: str = "access"


class UserCreate(BaseModel):
    """Schema for creating a new user"""

    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    full_name: Optional[str] = None


class UserUpdate(BaseModel):
    """Schema for updating user information"""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8)


class UserResponse(BaseModel):
    """User response schema (excludes sensitive data)"""

    id: UUID
    email: str
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime


class UserLogin(BaseModel):
    """Login request schema"""

    email: EmailStr
    password: str


class OrganizationCreate(BaseModel):
    """Schema for creating an organization"""

    name: str = Field(..., min_length=1, max_length=100)


class OrganizationResponse(BaseModel):
    """Organization response schema"""

    id: UUID
    name: str
    created_at: datetime


class OrganizationMemberAdd(BaseModel):
    """Schema for adding a member to an organization"""

    user_id: UUID
    role: str = Field(default="member", pattern="^(owner|admin|member)$")
