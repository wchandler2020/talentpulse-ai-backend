from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone

from .models import Job, JobSkill
from .serializers import (
    JobSerializer,
    JobCreateUpdateSerializer,
    JobListSerializer,
    JobSkillSerializer,
)

from talentpulse.permissions import IsRecruiter

class JobViewSet(viewsets.ModelViewSet):
    """
        Recruiters can create/update/delete.
        Candidates can only view published jobs.
    """
    queryset = Job.objects.prefetch_related('skills').all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'employment_type', 'experience_level', 'is_remote']
    search_fields = ['title', 'department', 'description', 'location']
    ordering_fields = ['created_at', 'published_at', 'title']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return JobListSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return JobCreateUpdateSerializer
        return JobSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Candidates only see published jobs
        role = getattr(self.request, 'user_role', 'CANDIDATE')
        if role == 'CANDIDATE':
            queryset = queryset.filter(status='PUBLISHED')
        return queryset

    def perform_create(self, serializer):
        serializer.save(clerk_user_id=self.request.clerk_user_id)

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """POST /jobs/{id}/publish/ — publish a draft job"""
        job = self.get_object()
        if job.status != 'DRAFT':
            return Response(
                {'error': 'Only draft jobs can be published.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        job.status = 'PUBLISHED'
        job.published_at = timezone.now()
        job.save()
        return Response(JobSerializer(job).data)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        """POST /jobs/{id}/close/ — close a published job"""
        job = self.get_object()
        job.status = 'CLOSED'
        job.save()
        return Response(JobSerializer(job).data)

    @action(detail=True, methods=['get'])
    def applications(self, request, pk=None):
        """GET /jobs/{id}/applications/ — all applications for a job"""
        from candidates.serializers import ApplicationListSerializer
        job = self.get_object()
        applications = job.applications.select_related(
            'candidate', 'score'
        ).prefetch_related('pipeline_events').all()
        serializer = ApplicationListSerializer(applications, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """GET /jobs/stats/ — quick stats for dashboard header"""
        queryset = self.get_queryset()
        return Response({
            'total': queryset.count(),
            'published': queryset.filter(status='PUBLISHED').count(),
            'draft': queryset.filter(status='DRAFT').count(),
            'closed': queryset.filter(status='CLOSED').count(),
        })
