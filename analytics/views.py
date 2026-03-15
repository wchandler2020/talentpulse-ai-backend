from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import timedelta

from .models import PipelineEvent, AIUsageLog, DashboardSnapshot
from .serializers import (
    PipelineEventSerializer,
    AIUsageLogSerializer,
    DashboardSnapshotSerializer,
)
from candidates.models import Application, Candidate
from jobs.models import Job


class PipelineEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read only — pipeline events are created automatically
    when applications move stages, never manually.
    """
    queryset            = PipelineEvent.objects.select_related(
                            'candidate', 'job', 'application'
                          ).all()
    serializer_class    = PipelineEventSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        # Filter by application if provided
        application_id = self.request.query_params.get('application')
        if application_id:
            queryset = queryset.filter(application_id=application_id)
        return queryset


class AIUsageLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read only — AI usage logs are created automatically
    by the AI service, never manually.
    """
    queryset            = AIUsageLog.objects.all()
    serializer_class    = AIUsageLogSerializer

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """GET /ai-usage/summary/ — cost and usage summary"""
        today       = timezone.now().date()
        last_30     = today - timedelta(days=30)

        logs        = self.get_queryset()
        today_logs  = logs.filter(created_at__date=today)
        month_logs  = logs.filter(created_at__date__gte=last_30)

        return Response({
            'today': {
                'calls':            today_logs.count(),
                'total_tokens':     sum(l.total_tokens for l in today_logs),
                'estimated_cost':   sum(float(l.estimated_cost_usd) for l in today_logs),
                'failures':         today_logs.filter(status='FAILED').count(),
            },
            'last_30_days': {
                'calls':            month_logs.count(),
                'total_tokens':     sum(l.total_tokens for l in month_logs),
                'estimated_cost':   sum(float(l.estimated_cost_usd) for l in month_logs),
                'by_action':        list(
                    month_logs.values('action')
                              .annotate(count=Count('id'))
                              .order_by('-count')
                ),
            },
        })


class DashboardViewSet(viewsets.ViewSet):
    """
    Aggregated dashboard metrics.
    Combines live counts with pre-computed snapshots.
    """

    @action(detail=False, methods=['get'])
    def overview(self, request):
        """
        GET /dashboard/overview/
        Main dashboard stats — jobs, applications, pipeline breakdown.
        """
        today   = timezone.now().date()
        last_7  = today - timedelta(days=7)
        last_30 = today - timedelta(days=30)

        # Job stats
        jobs = Job.objects.all()
        job_stats = {
            'total':        jobs.count(),
            'published':    jobs.filter(status='PUBLISHED').count(),
            'draft':        jobs.filter(status='DRAFT').count(),
            'closed':       jobs.filter(status='CLOSED').count(),
        }

        # Application stats
        applications = Application.objects.all()
        app_stats = {
            'total':        applications.count(),
            'today':        applications.filter(applied_at__date=today).count(),
            'last_7_days':  applications.filter(applied_at__date__gte=last_7).count(),
            'last_30_days': applications.filter(applied_at__date__gte=last_30).count(),
        }

        # Pipeline stage breakdown
        stage_breakdown = dict(
            applications.values('stage')
                        .annotate(count=Count('id'))
                        .values_list('stage', 'count')
        )

        # Candidate stats
        candidate_stats = {
            'total':    Candidate.objects.count(),
            'active':   Candidate.objects.filter(status='ACTIVE').count(),
        }

        # Conversion rates
        total       = applications.count() or 1
        screened    = applications.filter(stage__in=['SCREENED', 'INTERVIEW', 'TECHNICAL', 'OFFER', 'HIRED']).count()
        interviewed = applications.filter(stage__in=['INTERVIEW', 'TECHNICAL', 'OFFER', 'HIRED']).count()
        offered     = applications.filter(stage__in=['OFFER', 'HIRED']).count()
        hired       = applications.filter(stage='HIRED').count()

        conversion = {
            'screen_rate':      round(screened / total * 100, 1),
            'interview_rate':   round(interviewed / total * 100, 1),
            'offer_rate':       round(offered / total * 100, 1),
            'hire_rate':        round(hired / total * 100, 1),
        }

        # Top jobs by application count
        top_jobs = list(
            jobs.filter(status='PUBLISHED')
                .annotate(app_count=Count('applications'))
                .order_by('-app_count')
                .values('id', 'title', 'department', 'app_count')[:5]
        )

        return Response({
            'jobs':             job_stats,
            'applications':     app_stats,
            'stage_breakdown':  stage_breakdown,
            'candidates':       candidate_stats,
            'conversion':       conversion,
            'top_jobs':         top_jobs,
        })

    @action(detail=False, methods=['get'])
    def pipeline(self, request):
        """
        GET /dashboard/pipeline/
        Full pipeline board data — all applications grouped by stage.
        """
        from candidates.serializers import ApplicationListSerializer

        stages = [
            'APPLIED', 'SCREENED', 'INTERVIEW',
            'TECHNICAL', 'OFFER', 'HIRED', 'REJECTED'
        ]

        applications = Application.objects.select_related(
            'candidate', 'job', 'score', 'resume'
        ).all()

        # Filter by job if provided
        job_id = request.query_params.get('job')
        if job_id:
            applications = applications.filter(job_id=job_id)

        pipeline = {}
        for stage in stages:
            stage_apps = applications.filter(stage=stage)
            pipeline[stage] = {
                'count':        stage_apps.count(),
                'applications': ApplicationListSerializer(stage_apps, many=True).data,
            }

        return Response(pipeline)
