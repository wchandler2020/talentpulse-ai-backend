from rest_framework import serializers
from .models import Candidate, Application, Resume, CandidateScore
from jobs.serializers import JobListSerializer


class CandidateSerializer(serializers.ModelSerializer):
    application_count = serializers.ReadOnlyField()
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = Candidate
        fields = [
            'id', 'clerk_user_id', 'first_name', 'last_name',
            'full_name', 'email', 'phone', 'location',
            'linkedin_url', 'portfolio_url', 'bio', 'status',
            'created_at', 'updated_at', 'application_count',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CandidateListSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    application_count = serializers.ReadOnlyField()

    class Meta:
        model = Candidate
        fields = [
            'id', 'full_name', 'email', 'location',
            'status', 'created_at', 'application_count',
        ]


class ResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resume
        fields = [
            'id', 'application', 'candidate', 's3_key', 's3_url',
            'file_name', 'file_size', 'parsed_skills',
            'parsed_experience', 'parsed_education',
            'parsed_summary', 'years_of_experience',
            'parse_status', 'parse_error', 'parsed_at',
            'uploaded_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 's3_key', 's3_url', 'parsed_skills',
            'parsed_experience', 'parsed_education',
            'parsed_summary', 'years_of_experience',
            'parse_status', 'parse_error', 'parsed_at',
            'uploaded_at', 'updated_at',
        ]


class CandidateScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateScore
        fields = [
            'id', 'application', 'candidate', 'job',
            'overall_score', 'skills_score', 'experience_score',
            'education_score', 'score_breakdown', 'strengths',
            'gaps', 'ai_reasoning', 'recommendation',
            'interview_questions', 'scored_at', 'updated_at',
            'model_version',
        ]
        read_only_fields = fields


class ApplicationListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for pipeline board and job application lists.
    """
    candidate_name = serializers.CharField(source='candidate.full_name', read_only=True)
    candidate_email = serializers.CharField(source='candidate.email', read_only=True)
    job_title = serializers.CharField(source='job.title', read_only=True)
    overall_score = serializers.FloatField(source='score.overall_score', read_only=True, default=None)
    resume_parse_status = serializers.CharField(source='resume.parse_status', read_only=True, default=None)
    has_resume = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            'id', 'candidate', 'candidate_name', 'candidate_email',
            'job', 'job_title', 'stage', 'source', 'is_flagged',
            'flag_reason', 'applied_at', 'updated_at',
            'stage_updated_at', 'overall_score',
            'resume_parse_status', 'has_resume',
        ]

    def get_has_resume(self, obj):
        return hasattr(obj, 'resume') and obj.resume is not None


class ApplicationDetailSerializer(serializers.ModelSerializer):
    """
    used  for single application view
    includes candidate, score, resume and job details.
    """
    candidate = CandidateSerializer(read_only=True)
    job = JobListSerializer(read_only=True)
    resume = ResumeSerializer(read_only=True)
    score = CandidateScoreSerializer(read_only=True)

    class Meta:
        model = Application
        fields = [
            'id', 'candidate', 'job', 'stage', 'cover_letter',
            'source', 'recruiter_notes', 'rejection_reason',
            'is_flagged', 'flag_reason', 'applied_at',
            'updated_at', 'stage_updated_at', 'resume', 'score',
        ]
        read_only_fields = ['id', 'applied_at', 'updated_at']


class ApplicationCreateSerializer(serializers.ModelSerializer):
    """
        Used when a candidate submits an application.
    """

    class Meta:
        model = Application
        fields = [
            'id', 'candidate', 'job', 'cover_letter', 'source',
        ]
        read_only_fields = ['id']

    def validate(self, data):
        # Prevent duplicate applications
        if Application.objects.filter(
            candidate=data['candidate'],
            job=data['job']
        ).exists():
            raise serializers.ValidationError(
                'This candidate has already applied to this job.'
            )
        # Prevent applying to non-published jobs
        if data['job'].status != 'PUBLISHED':
            raise serializers.ValidationError(
                'This job is not currently accepting applications.'
            )
        return data


class StageUpdateSerializer(serializers.Serializer):
    """
        Used when a recruiter moves a candidate through the process.
    """
    stage = serializers.ChoiceField(choices=Application.STAGE_CHOICES)
    notes = serializers.CharField(required=False, allow_blank=True)