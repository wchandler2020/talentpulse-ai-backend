from rest_framework import serializers
from .models import PipelineEvent, AIUsageLog, DashboardSnapshot


class PipelineEventSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source='candidate.full_name', read_only=True)
    job_title = serializers.CharField(source='job.title', read_only=True)

    class Meta:
        model = PipelineEvent
        fields = [
            'id', 'application', 'candidate', 'candidate_name',
            'job', 'job_title', 'from_stage', 'to_stage',
            'moved_by_clerk_id', 'notes', 'created_at',
        ]
        read_only_fields = fields


class AIUsageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIUsageLog
        fields = [
            'id', 'action', 'triggered_by', 'related_application',
            'related_job', 'model', 'prompt_tokens', 'completion_tokens',
            'total_tokens', 'estimated_cost_usd', 'status',
            'error_message', 'response_time_ms', 'created_at',
        ]
        read_only_fields = fields


class DashboardSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardSnapshot
        fields = [
            'id', 'snapshot_date', 'total_jobs_active',
            'total_applications', 'new_applications_today',
            'total_candidates', 'stage_breakdown', 'screen_rate',
            'interview_rate', 'offer_rate', 'hire_rate',
            'ai_calls_today', 'ai_cost_today_usd',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields