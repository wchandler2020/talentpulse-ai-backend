from django.db import models
from jobs.models import Job


class Candidate(models.Model):

    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('BLACKLISTED', 'Blacklisted'),
    ]

    # Clerk integration — one candidate profile per Clerk user
    clerk_user_id = models.CharField(max_length=255, unique=True)

    # Personal info
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    location = models.CharField(max_length=255, blank=True)
    linkedin_url = models.URLField(blank=True)
    portfolio_url = models.URLField(blank=True)
    bio = models.TextField(blank=True)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['clerk_user_id']),
            models.Index(fields=['email']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def application_count(self):
        return self.applications.count()


class Application(models.Model):

    STAGE_CHOICES = [
        ('APPLIED', 'Applied'),
        ('SCREENED', 'Screened'),
        ('INTERVIEW', 'Interview'),
        ('TECHNICAL', 'Technical Assessment'),
        ('OFFER', 'Offer'),
        ('HIRED', 'Hired'),
        ('REJECTED', 'Rejected'),
        ('WITHDRAWN', 'Withdrawn'),
    ]

    SOURCE_CHOICES = [
        ('DIRECT', 'Direct Application'),
        ('LINKEDIN', 'LinkedIn'),
        ('REFERRAL', 'Referral'),
        ('INDEED', 'Indeed'),
        ('OTHER', 'Other'),
    ]

    # Relationships
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='applications')
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='applications')

    # Application details
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='APPLIED')
    cover_letter = models.TextField(blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='DIRECT')

    # Recruiter notes
    recruiter_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    # Flags
    is_flagged = models.BooleanField(default=False)  # Flagged for attention
    flag_reason = models.TextField(blank=True)

    # Metadata
    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    stage_updated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-applied_at']
        # Prevent a candidate from applying to the same job twice
        unique_together = ['candidate', 'job']
        indexes = [
            models.Index(fields=['stage']),
            models.Index(fields=['applied_at']),
            models.Index(fields=['is_flagged']),
        ]

    def __str__(self):
        return f"{self.candidate.full_name} → {self.job.title} ({self.stage})"


class Resume(models.Model):

    PARSE_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    # Relationships
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name='resume')
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='resumes')

    # File storage
    s3_key = models.CharField(max_length=500)       # S3 object key
    s3_url = models.URLField(max_length=1000)        # Full S3 URL
    file_name = models.CharField(max_length=255)
    file_size = models.IntegerField(null=True, blank=True)  # Bytes

    # AI parsed content — stored as JSON
    parsed_skills = models.JSONField(default=list, blank=True)
    parsed_experience = models.JSONField(default=list, blank=True)
    parsed_education = models.JSONField(default=list, blank=True)
    parsed_summary = models.TextField(blank=True)
    years_of_experience = models.FloatField(null=True, blank=True)

    # Parse status
    parse_status = models.CharField(max_length=20, choices=PARSE_STATUS_CHOICES, default='PENDING')
    parse_error = models.TextField(blank=True)
    parsed_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Resume — {self.candidate.full_name} ({self.parse_status})"


class CandidateScore(models.Model):

    # Relationships
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name='score')
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='scores')
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='candidate_scores')

    # AI scoring
    overall_score = models.FloatField()                    # 0.0 - 100.0
    skills_score = models.FloatField(null=True, blank=True)
    experience_score = models.FloatField(null=True, blank=True)
    education_score = models.FloatField(null=True, blank=True)

    # Score breakdown and reasoning stored as JSON
    score_breakdown = models.JSONField(default=dict)
    strengths = models.JSONField(default=list)         # List of strength strings
    gaps = models.JSONField(default=list)         # List of gap strings
    ai_reasoning = models.TextField(blank=True)           # Full AI explanation
    recommendation = models.CharField(max_length=20, blank=True)  # STRONG_YES / YES / MAYBE / NO

    # Generated interview questions
    interview_questions = models.JSONField(default=list)

    # Metadata
    scored_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    model_version = models.CharField(max_length=50, default='gpt-4o')

    class Meta:
        ordering = ['-overall_score']
        indexes = [
            models.Index(fields=['overall_score']),
        ]

    def __str__(self):
        return f"{self.candidate.full_name} — {self.job.title} — Score: {self.overall_score}"
