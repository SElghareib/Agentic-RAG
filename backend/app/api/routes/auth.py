"""Authentication routes for user registration, login, and organization management"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_current_user
from app.core.security import create_access_token, verify_password, get_password_hash
from app.models.user import User, Organization, OrganizationMember
from app.schemas.auth import (
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
    OrganizationCreate,
    OrganizationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """Register a new user account
    
    Creates a new user with the provided email and password.
    Email must be unique across the system.
    """
    # Check if user already exists
    from sqlalchemy import select
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    
    # Create new user
    new_user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        is_active=True,
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    logger.info(f"New user registered: {new_user.email}")
    
    return new_user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db_session),
):
    """Login and receive JWT access token
    
    Uses OAuth2 password flow. Username is the user's email.
    Returns access_token and token_type for use in Authorization header.
    """
    from sqlalchemy import select
    
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == form_data.username)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user.id)})
    
    logger.info(f"User logged in: {user.email}")
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get current authenticated user information"""
    return current_user


@router.post("/organizations", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    org_data: OrganizationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new organization
    
    The creating user becomes the owner of the organization.
    """
    from sqlalchemy import select
    
    # Check for duplicate organization name for this user
    result = await db.execute(
        select(Organization).where(
            Organization.name == org_data.name,
            Organization.members.any(OrganizationMember.user_id == current_user.id)
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already belong to an organization with this name",
        )
    
    # Create organization
    new_org = Organization(name=org_data.name)
    db.add(new_org)
    await db.flush()  # Get the ID
    
    # Add creator as owner
    membership = OrganizationMember(
        organization_id=new_org.id,
        user_id=current_user.id,
        role="owner",
    )
    db.add(membership)
    await db.commit()
    await db.refresh(new_org)
    
    logger.info(f"Organization created: {new_org.name} by user {current_user.email}")
    
    return new_org


@router.get("/organizations", response_model=list[OrganizationResponse])
async def list_user_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """List all organizations the current user belongs to"""
    from sqlalchemy import select
    
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember)
        .where(OrganizationMember.user_id == current_user.id)
        .order_by(Organization.created_at)
    )
    organizations = result.scalars().all()
    
    return organizations


@router.get("/organizations/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get details of a specific organization"""
    from sqlalchemy import select
    
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember)
        .where(
            Organization.id == org_id,
            OrganizationMember.user_id == current_user.id
        )
    )
    organization = result.scalar_one_or_none()
    
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found or access denied",
        )
    
    return organization
