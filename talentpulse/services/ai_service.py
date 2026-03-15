import anthropic
import base64
import json
import logging
import time
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Cost per million tokens for claude-sonnet-4-6 (update if model changes)
COST_PER_INPUT_TOKEN    = 0.000003
COST_PER_OUTPUT_TOKEN   = 0.000015
MODEL                   = "claude-sonnet-4-6"


def get_client():
    """Returns a configured Anthropic client."""
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _log_ai_usage(
    action: str,
    triggered_by: str,
    input_tokens: int,
    output_tokens: int,
    status: str,
    response_time_ms: int,
    error_message: str = '',
    application=None,
    job=None,
):
    """
    Logs every Claude API call to AIUsageLog.
    Keeps track of cost and usage for the analytics dashboard.
    """
    from analytics.models import AIUsageLog

    total_tokens    = input_tokens + output_tokens
    estimated_cost  = (
        (input_tokens  * COST_PER_INPUT_TOKEN) +
        (output_tokens * COST_PER_OUTPUT_TOKEN)
    )

    AIUsageLog.objects.create(
        action              = action,
        triggered_by        = triggered_by,
        related_application = application,
        related_job         = job,
        model               = MODEL,
        prompt_tokens       = input_tokens,
        completion_tokens   = output_tokens,
        total_tokens        = total_tokens,
        estimated_cost_usd  = estimated_cost,
        status              = status,
        error_message       = error_message,
        response_time_ms    = response_time_ms,
    )


def parse_resume(resume_id: int, triggered_by: str):
    """
    Fetches a resume PDF from S3, sends it to Claude,
    and extracts structured data (skills, experience, education).

    Updates the Resume model with parsed results.
    """
    from candidates.models import Resume
    from .s3_service import download_file_as_bytes

    # Fetch resume record
    try:
        resume = Resume.objects.select_related(
            'candidate', 'application__job'
        ).get(id=resume_id)
    except Resume.DoesNotExist:
        logger.error(f"Resume {resume_id} not found")
        return

    # Mark as processing
    resume.parse_status = 'PROCESSING'
    resume.save()

    start_time = time.time()

    try:
        # Download PDF from S3
        pdf_bytes = download_file_as_bytes(resume.s3_key)
        if not pdf_bytes:
            raise ValueError(f"Could not download resume from S3: {resume.s3_key}")

        # Encode PDF as base64 for Claude
        pdf_base64 = base64.standard_b64encode(pdf_bytes).decode('utf-8')

        # Build the prompt
        job         = resume.application.job
        prompt      = f"""
You are an expert technical recruiter and resume parser.

Analyze this resume PDF and extract structured information.
The candidate is applying for the role of: {job.title}
Required skills for this role: {', '.join([s.name for s in job.skills.filter(skill_type='REQUIRED')])}

Return ONLY a valid JSON object with exactly this structure, no other text:
{{
    "full_name": "candidate full name",
    "email": "email if found",
    "phone": "phone if found",
    "location": "city, state if found",
    "summary": "2-3 sentence professional summary based on their experience",
    "years_of_experience": 5.5,
    "skills": ["skill1", "skill2", "skill3"],
    "experience": [
        {{
            "company": "Company Name",
            "title": "Job Title",
            "start_date": "MM/YYYY",
            "end_date": "MM/YYYY or Present",
            "duration_months": 18,
            "description": "brief description of role and achievements"
        }}
    ],
    "education": [
        {{
            "institution": "University Name",
            "degree": "Bachelor of Science",
            "field": "Computer Science",
            "graduation_year": 2019
        }}
    ]
}}
"""

        client      = get_client()
        response    = client.messages.create(
            model       = MODEL,
            max_tokens  = 2000,
            messages    = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type":         "base64",
                                "media_type":   "application/pdf",
                                "data":         pdf_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        response_time_ms = int((time.time() - start_time) * 1000)

        # Parse the JSON response
        raw_text    = response.content[0].text.strip()
        # Strip markdown code fences if Claude adds them
        if raw_text.startswith('```'):
            raw_text = raw_text.split('```')[1]
            if raw_text.startswith('json'):
                raw_text = raw_text[4:]
        parsed_data = json.loads(raw_text)

        # Update Resume record with parsed data
        resume.parsed_skills        = parsed_data.get('skills', [])
        resume.parsed_experience    = parsed_data.get('experience', [])
        resume.parsed_education     = parsed_data.get('education', [])
        resume.parsed_summary       = parsed_data.get('summary', '')
        resume.years_of_experience  = parsed_data.get('years_of_experience')
        resume.parse_status         = 'COMPLETED'
        resume.parsed_at            = timezone.now()
        resume.save()

        # Log successful usage
        _log_ai_usage(
            action              = 'RESUME_PARSE',
            triggered_by        = triggered_by,
            input_tokens        = response.usage.input_tokens,
            output_tokens       = response.usage.output_tokens,
            status              = 'SUCCESS',
            response_time_ms    = response_time_ms,
            application         = resume.application,
        )

        logger.info(f"Resume {resume_id} parsed successfully")
        return resume

    except Exception as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Resume parsing failed for {resume_id}: {e}")

        # Mark as failed
        resume.parse_status = 'FAILED'
        resume.parse_error  = str(e)
        resume.save()

        _log_ai_usage(
            action              = 'RESUME_PARSE',
            triggered_by        = triggered_by,
            input_tokens        = 0,
            output_tokens       = 0,
            status              = 'FAILED',
            response_time_ms    = response_time_ms,
            error_message       = str(e),
        )


def score_candidate(application, triggered_by: str):
    """
    Scores a candidate against job requirements using Claude.
    Returns a CandidateScore object with 0-100 score and detailed reasoning.
    """
    from candidates.models import CandidateScore

    start_time  = time.time()
    job         = application.job
    resume      = application.resume
    candidate   = application.candidate

    # Build required and preferred skills lists
    required_skills     = list(job.skills.filter(skill_type='REQUIRED').values_list('name', flat=True))
    preferred_skills    = list(job.skills.filter(skill_type='PREFERRED').values_list('name', flat=True))

    prompt = f"""
You are a senior technical recruiter scoring a candidate for a job opening.

JOB DETAILS:
- Title: {job.title}
- Experience Level: {job.experience_level}
- Employment Type: {job.employment_type}
- Required Skills: {', '.join(required_skills)}
- Preferred Skills: {', '.join(preferred_skills)}
- Job Description: {job.description[:1000]}

CANDIDATE DETAILS:
- Name: {candidate.full_name}
- Years of Experience: {resume.years_of_experience}
- Skills: {', '.join(resume.parsed_skills)}
- Summary: {resume.parsed_summary}
- Experience: {json.dumps(resume.parsed_experience[:3])}
- Education: {json.dumps(resume.parsed_education)}

Score this candidate and return ONLY a valid JSON object with this exact structure:
{{
    "overall_score": 85.5,
    "skills_score": 90.0,
    "experience_score": 80.0,
    "education_score": 85.0,
    "recommendation": "STRONG_YES",
    "strengths": [
        "Has 5+ years in Python matching job requirement",
        "Led teams of 3-5 engineers"
    ],
    "gaps": [
        "No direct AWS experience mentioned",
        "Missing required skill: Kubernetes"
    ],
    "score_breakdown": {{
        "required_skills_match": 8,
        "preferred_skills_match": 3,
        "experience_years_match": true,
        "seniority_match": true
    }},
    "reasoning": "2-3 paragraph explanation of the score",
    "interview_questions": [
        "Tell me about your experience with...",
        "How have you handled...",
        "Describe a time when..."
    ]
}}

Scoring guide:
- overall_score: 0-100 float
- recommendation: STRONG_YES (85+), YES (70-84), MAYBE (50-69), NO (below 50)
- Generate exactly 5 interview questions tailored to this specific candidate and role
"""

    try:
        client      = get_client()
        response    = client.messages.create(
            model       = MODEL,
            max_tokens  = 1500,
            messages    = [{"role": "user", "content": prompt}],
        )

        response_time_ms = int((time.time() - start_time) * 1000)

        # Parse response
        raw_text = response.content[0].text.strip()
        if raw_text.startswith('```'):
            raw_text = raw_text.split('```')[1]
            if raw_text.startswith('json'):
                raw_text = raw_text[4:]
        data = json.loads(raw_text)

        # Create or update CandidateScore
        candidate_score, _ = CandidateScore.objects.update_or_create(
            application = application,
            defaults    = {
                'candidate': candidate,
                'job': job,
                'overall_score': data.get('overall_score', 0),
                'skills_score': data.get('skills_score'),
                'experience_score': data.get('experience_score'),
                'education_score': data.get('education_score'),
                'score_breakdown': data.get('score_breakdown', {}),
                'strengths': data.get('strengths', []),
                'gaps': data.get('gaps', []),
                'ai_reasoning': data.get('reasoning', ''),
                'recommendation': data.get('recommendation', ''),
                'interview_questions': data.get('interview_questions', []),
                'model_version': MODEL,
            }
        )

        # Log usage
        _log_ai_usage(
            action = 'CANDIDATE_SCORE',
            triggered_by = triggered_by,
            input_tokens = response.usage.input_tokens,
            output_tokens = response.usage.output_tokens,
            status = 'SUCCESS',
            response_time_ms = response_time_ms,
            application = application,
            job = job,
        )

        logger.info(f"Scored candidate {candidate.full_name} for {job.title}: {data.get('overall_score')}")
        return candidate_score

    except Exception as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Candidate scoring failed: {e}")

        _log_ai_usage(
            action = 'CANDIDATE_SCORE',
            triggered_by = triggered_by,
            input_tokens = 0,
            output_tokens = 0,
            status = 'FAILED',
            response_time_ms = response_time_ms,
            error_message = str(e),
            application = application,
            job = job,
        )
        raise


def parse_resume_async(resume_id: int, triggered_by: str):
    """
    Entry point called from the upload_resume view.
    In production this would be a Celery task for true async processing.
    For now runs synchronously — fast enough for a portfolio project.
    """
    parse_resume(resume_id, triggered_by)