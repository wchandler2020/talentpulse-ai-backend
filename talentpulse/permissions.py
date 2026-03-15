from rest_framework.permissions import BasePermission


class IsRecruiter(BasePermission):
    """
    Allows access only to users with the RECRUITER
    or ADMIN role set by Clerk middleware.
    """
    def has_permission(self, request, view):
        return getattr(request, 'user_role', None) in ['RECRUITER', 'ADMIN']


class IsCandidate(BasePermission):
    """
    Allows access only to users with the CANDIDATE role.
    """
    def has_permission(self, request, view):
        return getattr(request, 'user_role', None) == 'CANDIDATE'


class IsRecruiterOrReadOnly(BasePermission):
    """
    Candidates can read, only recruiters can write.
    """
    def has_permission(self, request, view):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return request.clerk_user_id is not None
        return getattr(request, 'user_role', None) in ['RECRUITER', 'ADMIN']