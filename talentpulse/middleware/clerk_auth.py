import jwt
import requests
import logging
from django.http import JsonResponse
from django.conf import settings
from functools import lru_cache

logger = logging.getLogger(__name__)

# Paths that don't require authentication
PUBLIC_PATHS = [
    '/admin/',
    '/api/v1/jobs/',         # Candidates can browse jobs without auth
]

EXEMPT_METHODS = ['OPTIONS']


@lru_cache(maxsize=1)
def get_clerk_public_keys():
    """
        Fetch Clerk's public JWKS keys.
        Cached so we don't hit Clerk's API on every request.
        Cache invalidates when the process restarts.
    """
    try:
        jwks_url = "https://api.clerk.com/v1/jwks"
        response = requests.get(
            jwks_url,
            headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"},
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch Clerk JWKS: {e}")
        return None


def get_token_from_request(request):
    """
        Extract Bearer token from Authorization header.
    """
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if auth_header.startswith('Bearer '):
        return auth_header.split(' ')[1]
    return None


def decode_clerk_token(token):
    """
    Decode and verify a Clerk JWT token.
    Returns the decoded payload or None if invalid.
    """
    try:
        jwks = get_clerk_public_keys()
        if not jwks:
            return None

        # Get the key id from the token header
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get('kid')

        # Find the matching public key
        public_key = None
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                break

        if not public_key:
            logger.warning("No matching public key found for token kid")
            return None

        # Decode and verify the token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=['RS256'],
            options={"verify_exp": True},
        )
        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("Clerk token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid Clerk token: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error decoding token: {e}")
        return None


class ClerkAuthMiddleware:
    """
        Middleware that validates Clerk JWT tokens on every request.

        Sets the following on the request object:
            request.clerk_user_id  — the authenticated user's Clerk ID
            request.user_role      — ADMIN / RECRUITER / CANDIDATE
            request.is_authenticated — True if token is valid

        Returns 401 if token is missing or invalid on protected routes.
        Returns 403 if token is valid but role is insufficient.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Always allow OPTIONS (CORS preflight)
        if request.method in EXEMPT_METHODS:
            return self.get_response(request)

        # Always allow admin
        if request.path.startswith('/admin/'):
            return self.get_response(request)

        # Extract token
        token = get_token_from_request(request)

        if not token:
            # Allow GET requests to public job listings without auth
            if request.method == 'GET' and self._is_public_path(request.path):
                request.clerk_user_id = None
                request.user_role = 'ANONYMOUS'
                request.is_authenticated = False
                return self.get_response(request)

            return JsonResponse(
                {'error': 'Authentication required. Please provide a Bearer token.'},
                status=401
            )

        # Decode and verify token
        payload = decode_clerk_token(token)

        if not payload:
            return JsonResponse(
                {'error': 'Invalid or expired token.'},
                status=401
            )

        # Attach user info to request
        request.clerk_user_id = payload.get('sub')
        request.user_role = payload.get('role', 'CANDIDATE').upper()
        request.is_authenticated = True
        request.token_payload = payload

        return self.get_response(request)

    def _is_public_path(self, path):
        return any(path.startswith(p) for p in PUBLIC_PATHS)