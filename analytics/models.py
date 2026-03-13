from django.db import models
from candidates.models import Application, Candidate
from jobs.models import Job


class PipelineEvent(models.Model):
    # Relationships
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='pipeline_events')
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='pipeline_events')
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='pipeline_events')

    # Stage transition
    from_stage = models.CharField(max_length=20, blank=True)  # Empty on first event
    to_stage = models.CharField(max_length=20)
    moved_by_clerk_id = models.CharField(max_length=255)             # Recruiter who moved it
    notes = models.TextField(blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['application']),
            models.Index(fields=['created_at']),
            models.Index(fields=['to_stage']),
        ]

    def __str__(self):
        return f"{self.candidate} | {self.from_stage} → {self.to_stage} | {self.created_at:%Y-%m-%d}"


class AIUsageLog(models.Model):
    """
        Tracks every OpenAI API call made by the platform.
        Important for cost monitoring and usage auditing
    """

    ACTION_CHOICES = [
        ('RESUME_PARSE', 'Resume Parse'),
        ('CANDIDATE_SCORE', 'Candidate Score'),
        ('INTERVIEW_QUESTIONS', 'Interview Questions'),
        ('JOB_INSIGHTS', 'Job Insights'),
    ]

    STATUS_CHOICES = [
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
        ('TIMEOUT', 'Timeout'),
    ]

    # What triggered this call
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    triggered_by = models.CharField(max_length=255)          # Clerk user ID
    related_application = models.ForeignKey(Application, on_delete=models.SET_NULL,
                                            null=True, blank=True,
                                            related_name='ai_logs')
    related_job = models.ForeignKey(Job, on_delete=models.SET_NULL,
                                            null=True, blank=True,
                                            related_name='ai_logs')

    # OpenAI usage details
    model = models.CharField(max_length=50, default='gpt-4o')
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    estimated_cost_usd = models.DecimalField(max_digits=8, decimal_places=6, default=0)

    # Result
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUCCESS')
    error_message = models.TextField(blank=True)
    response_time_ms = models.IntegerField(default=0)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action']),
            models.Index(fields=['created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.action} | {self.status} | {self.total_tokens} tokens | {self.created_at:%Y-%m-%d}"


class DashboardSnapshot(models.Model):
    """
        Daily pre-computed analytics snapshot.
        Avoids running expensive aggregation queries
        on every dashboard load in production.
    """

    snapshot_date = models.DateField(unique=True)

    # Pipeline counts
    total_jobs_active = models.IntegerField(default=0)
    total_applications = models.IntegerField(default=0)
    new_applications_today = models.IntegerField(default=0)
    total_candidates = models.IntegerField(default=0)

    # Stage breakdown stored as JSON
    # e.g. {"APPLIED": 120, "SCREENED": 45, "INTERVIEW": 20}
    stage_breakdown = models.JSONField(default=dict)

    # Conversion rates
    screen_rate = models.FloatField(default=0)   # Applied → Screened
    interview_rate = models.FloatField(default=0)   # Screened → Interview
    offer_rate = models.FloatField(default=0)   # Interview → Offer
    hire_rate = models.FloatField(default=0)   # Offer → Hired

    # AI usage summary
    ai_calls_today = models.IntegerField(default=0)
    ai_cost_today_usd = models.DecimalField(max_digits=8, decimal_places=4, default=0)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-snapshot_date']

    def __str__(self):
        return f"Dashboard Snapshot — {self.snapshot_date}"
