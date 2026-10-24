"""Authentication & User Identity Endpoints."""
from fastapi import APIRouter, Depends
from auth import AuthenticatedUser, get_current_user, DEMO_USERS

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me", response_model=AuthenticatedUser)
def get_my_identity(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Return the authenticated user's verified identity."""
    return current_user


@router.get("/demo-tokens")
def list_demo_tokens():
    """List available demo tokens for team testing."""
    return {
        "description": "Sử dụng các token này trong tiêu đề 'Authorization: Bearer <token>' để kiểm thử.",
        "tokens": {
            token: {
                "user_id": str(user.user_id),
                "email": user.email,
                "role": user.role,
                "name": user.full_name
            }
            for token, user in DEMO_USERS.items()
        }
    }
