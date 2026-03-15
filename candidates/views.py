from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
import boto3
import uuid
import os

from .models import Candidate, Application, Resume, CandidateScore
from .serializers import (
    CandidateSerializer,
    CandidateListSerializer,
    ApplicationListSerializer,
    ApplicationDetailSerializer,
    ApplicationCreateSerializer,
    StageUpdateSerializer,
    ResumeSerializer,
    CandidateScoreSerializer,
)
from analytics.models import PipelineEvent, AIUsageLog
from talentpulse.permissions import IsRecruiter, IsRecruiterOrReadOnly


class CandidateViewSet(viewsets.ModelViewSet):
    queryset = Candidate.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['first_name', 'last_name', 'email', 'location']
    ordering_fields = ['created_at', 'first_name', 'last_name']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return CandidateListSerializer
        return CandidateSerializer

    def perform_create(self, serializer):
        serializer.save(clerk_user_id=self.request.clerk_user_id)

    @action(detail=True, methods=['get'])
    def applications(self, request, pk=None):
        """
            GET /candidates/{id}/applications/
        """
        candidate = self.get_object()
        applications = candidate.applications.select_related(
            'job', 'score', 'resume'
        ).all()
        serializer = ApplicationListSerializer(applications, many=True)
        return Response(serializer.data)


class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = Application.objects.select_related(
        'candidate', 'job', 'score', 'resume'
    ).all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['stage', 'source', 'is_flagged', 'job']
    search_fields = ['candidate__first_name', 'candidate__last_name',
                        'candidate__email', 'job__title']
    ordering_fields = ['applied_at', 'stage_updated_at']
    ordering = ['-applied_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return ApplicationListSerializer
        if self.action == 'create':
            return ApplicationCreateSerializer
        return ApplicationDetailSerializer

    @action(detail=True, methods=['post'])
    def move_stage(self, request, pk=None):
        """
            POST /applications/{id}/move_stage/
            Moves candidate to next pipeline stage and logs the event.
        """
        application = self.get_object()
        serializer = StageUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from_stage = application.stage
        to_stage = serializer.validated_data['stage']
        notes = serializer.validated_data.get('notes', '')

        # Update application stage
        application.stage = to_stage
        application.stage_updated_at= timezone.now()
        application.save()

        # Log the pipeline event for analytics
        PipelineEvent.objects.create(
            application = application,
            candidate = application.candidate,
            job = application.job,
            from_stage = from_stage,
            to_stage = to_stage,
            moved_by_clerk_id = request.clerk_user_id,
            notes = notes,
        )

        return Response(ApplicationDetailSerializer(application).data)

    @action(detail=True, methods=['post'])
    def flag(self, request, pk=None):
        """POST /applications/{id}/flag/ — flag for attention"""
        application = self.get_object()
        application.is_flagged = not application.is_flagged
        application.flag_reason = request.data.get('reason', '')
        application.save()
        return Response(ApplicationDetailSerializer(application).data)

    @action(detail=True, methods=['post'])
    def upload_resume(self, request, pk=None):
        """
        POST /applications/{id}/upload_resume/
        Uploads resume PDF to AWS S3 and triggers AI parsing.
        """
        application = self.get_object()
        file = request.FILES.get('resume')

        if not file:
            return Response(
                {'error': 'No file provided.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not file.name.endswith('.pdf'):
            return Response(
                {'error': 'Only PDF files are accepted.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Upload to S3
        s3_client = boto3.client('s3')
        bucket = os.getenv('AWS_STORAGE_BUCKET_NAME')
        s3_key = f"resumes/{application.candidate.clerk_user_id}/{uuid.uuid4()}.pdf"

        try:
            s3_client.upload_fileobj(
                file,
                bucket,
                s3_key,
                ExtraArgs={'ContentType': 'application/pdf'}
            )
            s3_url = f"https://{bucket}.s3.amazonaws.com/{s3_key}"
        except Exception as e:
            return Response(
                {'error': f'S3 upload failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Create or update Resume record
        resume, _ = Resume.objects.update_or_create(
            application = application,
            defaults = {
                'candidate': application.candidate,
                's3_key': s3_key,
                's3_url': s3_url,
                'file_name': file.name,
                'file_size': file.size,
                'parse_status': 'PENDING',
            }
        )

        from talentpulse.services.ai_service import parse_resume_async
        parse_resume_async(resume.id, request.clerk_user_id)

        return Response(ResumeSerializer(resume).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def score(self, request, pk=None):
        """
        POST /applications/{id}/score/
        Triggers AI scoring of candidate against job requirements.
        """
        application = self.get_object()

        if not hasattr(application, 'resume') or application.resume.parse_status != 'COMPLETED':
            return Response(
                {'error': 'Resume must be uploaded and parsed before scoring.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from talentpulse.services.ai_service import score_candidate
        candidate_score = score_candidate(application, request.clerk_user_id)

        return Response(CandidateScoreSerializer(candidate_score).data)
        # return Response({'message': 'AI scoring service coming soon.'})

