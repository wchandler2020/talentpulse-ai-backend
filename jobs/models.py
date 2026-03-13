from django.db import models

# Create your models here.

class Job(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PUBLISHED', 'Published'),
        ('CLOSED', 'Closed'),
        ('ON_HOLD', 'On Hold'),
    ]

    EMPLOYMENT_TYPE_CHOICES = [
        ('FULL_TIME', 'Full Time'),
        ('PART_TIME', 'Part Time'),
        ('CONTRACT', 'Contract'),
        ('INTERNSHIP', 'Internship'),
    ]

    EXPERIENCE_LEVEL_CHOICES = [
        ('ENTRY', 'Entry Level'),
        ('MID', 'Mid Level'),
        ('SENIOR', 'Senior Level'),
        ('LEAD', 'Lead'),
        ('EXECUTIVE', 'Executive'),
    ]

    title = models.CharField(max_length=255)
    department = models.CharField(max_length=255, blank=True)
    description = models.TextField()
    requirements = models.TextField()
    responsibilities = models.TextField()
    employment_type = models.CharField(max_length=50, choices=EMPLOYMENT_TYPE_CHOICES, default='FULL_TIME')
    experience_level = models.CharField(max_length=50, choices=EXPERIENCE_LEVEL_CHOICES, default='MID')
    location = models.CharField(max_length=255, blank=True)
    is_remote = models.BooleanField(default=False)
    salary_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    salary_currency = models.CharField(max_length=10, default='USD')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    clerk_user_id = models.CharField(max_length=255)  # Clerk user who created the job
    hiring_manager_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['clerk_user_id']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.title} ({self.status})'

    @property
    def application_count(self):
        return self.applications.count()


    @property
    def salary_range_display(self):
        if self.salary_min and self.salary_max:
            return f"{self.salary_currency} {self.salary_min:,.0f} - {self.salary_max:,.0f}"
        return 'Not Specified'

class JobSkill(models.Model):
    SKILL_TYPE_CHOICES = [
        ('REQUIRED', 'Required'),
        ('PREFERRED', 'Preferred'),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='skills')
    name = models.CharField(max_length=100)
    skill_type = models.CharField(max_length=20, choices=SKILL_TYPE_CHOICES, default='REQUIRED')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['skill_type', 'name']
        unique_together = ['job', 'name']

    def __str__(self):
        return f"{self.name} ({self.skill_type}) — {self.job.title}"
