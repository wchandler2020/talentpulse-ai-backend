from rest_framework import serializers
from .models import Job, JobSkill


class JobSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobSkill
        fields = ['id', 'name', 'skill_type', 'created_at']
        read_only_fields = ['id', 'created_at']


class JobSerializer(serializers.ModelSerializer):
    skills = JobSkillSerializer(many=True, read_only=True)
    application_count = serializers.ReadOnlyField()
    salary_range_display = serializers.ReadOnlyField()

    class Meta:
        model = Job
        fields = [
            'id', 'title', 'department', 'description', 'requirements',
            'responsibilities', 'employment_type', 'experience_level',
            'location', 'is_remote', 'salary_min', 'salary_max',
            'salary_currency', 'status', 'clerk_user_id',
            'hiring_manager_name', 'created_at', 'updated_at',
            'published_at', 'closes_at', 'skills',
            'application_count', 'salary_range_display',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class JobCreateUpdateSerializer(serializers.ModelSerializer):
    """
        Used for POST and PUT/PATCH requests.
        Handles nested skill creation.
    """
    skills = JobSkillSerializer(many=True, required=False)

    class Meta:
        model = Job
        fields = [
            'id', 'title', 'department', 'description', 'requirements',
            'responsibilities', 'employment_type', 'experience_level',
            'location', 'is_remote', 'salary_min', 'salary_max',
            'salary_currency', 'status', 'clerk_user_id',
            'hiring_manager_name', 'published_at', 'closes_at', 'skills',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        skills_data = validated_data.pop('skills', [])
        job = Job.objects.create(**validated_data)
        for skill in skills_data:
            JobSkill.objects.create(job=job, **skill)
        return job

    def update(self, instance, validated_data):
        skills_data = validated_data.pop('skills', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if skills_data is not None:
            instance.skills.all().delete()
            for skill in skills_data:
                JobSkill.objects.create(job=instance, **skill)
        return instance


class JobListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for list views —
    avoids fetching unnecessary fields at scale.
    """
    application_count = serializers.ReadOnlyField()
    skill_count = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            'id', 'title', 'department', 'employment_type',
            'experience_level', 'location', 'is_remote',
            'status', 'created_at', 'published_at',
            'application_count', 'skill_count',
            'salary_min', 'salary_max', 'salary_currency',
        ]

    def get_skill_count(self, obj):
        return obj.skills.count()