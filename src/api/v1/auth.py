"""Authentication & User Identity Endpoints."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from auth import AuthenticatedUser, get_current_user, DEMO_USERS
from schemas.models import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    """Authenticate via email or demo token and return a bearer access token."""
    input_val = body.email_or_token.strip()

    # 1. Match token directly
    if input_val in DEMO_USERS:
        user = DEMO_USERS[input_val]
        return LoginResponse(
            access_token=input_val,
            token_type="bearer",
            user_id=user.user_id,
            email=user.email,
            full_name=user.full_name,
            role=user.role
        )

    # 2. Match email of demo user
    for token, user in DEMO_USERS.items():
        if user.email.lower() == input_val.lower():
            return LoginResponse(
                access_token=token,
                token_type="bearer",
                user_id=user.user_id,
                email=user.email,
                full_name=user.full_name,
                role=user.role
            )

    # 3. Match direct UUID
    try:
        user_uuid = uuid.UUID(input_val)
        return LoginResponse(
            access_token=str(user_uuid),
            token_type="bearer",
            user_id=user_uuid,
            email=f"user_{str(user_uuid)[:8]}@test.local",
            full_name=f"User {str(user_uuid)[:8]}",
            role="STUDENT"
        )
    except ValueError:
        pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Thông tin đăng nhập không hợp lệ. Hãy sử dụng email hoặc demo token (ví dụ: token_student_1, token_admin)."
    )


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

