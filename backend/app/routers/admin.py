


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from backend.app.core.database import get_db
from backend.app.core.security import require_admin, get_current_user
from backend.app.models.user import User, UserRole

router = APIRouter()


class UserListItem(BaseModel):
    id: int
    full_name: str
    email: str
    role: UserRole
    is_active: bool
    model_config = {"from_attributes": True}


class RoleUpdateRequest(BaseModel):
    role: UserRole


@router.get("/users", response_model=List[UserListItem])
def list_users(
    role: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all users. Optionally filter by ?role=student|teacher|admin."""
    query = db.query(User)
    if role:
        try:
            query = query.filter(User.role == UserRole(role))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid role: {role}")
    return query.order_by(User.full_name).all()


@router.get("/users/students", response_model=List[UserListItem])
def list_students(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all student accounts.
    Accessible by admin AND teacher (needed for quiz enrollment UI).
    """
    from backend.app.core.security import require_teacher
    if current_user.role not in (UserRole.admin, UserRole.teacher):
        raise HTTPException(status_code=403, detail="Teacher or admin required")
    return db.query(User).filter(User.role == UserRole.student).order_by(User.full_name).all()


@router.patch("/users/{user_id}/role", response_model=UserListItem)
def update_user_role(
    user_id: int,
    payload: RoleUpdateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Promote or demote a user's role. Admin only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    user.role = payload.role
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/activate")
def toggle_user_active(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Enable or disable a user account."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    user.is_active = not user.is_active
    db.commit()
    return {"id": user.id, "email": user.email, "is_active": user.is_active}


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Permanently delete a user. Admin only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    db.delete(user)
    db.commit()
