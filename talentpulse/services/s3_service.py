import boto3
import logging
import os
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def get_s3_client():
    """Returns a configured S3 client."""
    return boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_S3_REGION_NAME', 'us-east-1'),
    )


def upload_file(file_obj, s3_key: str, content_type: str = 'application/pdf') -> dict:
    """
    Upload a file object to S3.
    Returns dict with s3_key and s3_url on success.
    """
    client  = get_s3_client()
    bucket  = os.getenv('AWS_STORAGE_BUCKET_NAME')

    try:
        client.upload_fileobj(
            file_obj,
            bucket,
            s3_key,
            ExtraArgs={'ContentType': content_type}
        )
        s3_url = f"https://{bucket}.s3.amazonaws.com/{s3_key}"
        logger.info(f"Successfully uploaded file to S3: {s3_key}")
        return {'success': True, 's3_key': s3_key, 's3_url': s3_url}

    except ClientError as e:
        logger.error(f"S3 upload failed for {s3_key}: {e}")
        return {'success': False, 'error': str(e)}


def download_file_as_bytes(s3_key: str) -> bytes | None:
    """
    Download a file from S3 and return its raw bytes.
    Used by the AI service to read resume PDFs.
    """
    client  = get_s3_client()
    bucket  = os.getenv('AWS_STORAGE_BUCKET_NAME')

    try:
        response = client.get_object(Bucket=bucket, Key=s3_key)
        return response['Body'].read()

    except ClientError as e:
        logger.error(f"S3 download failed for {s3_key}: {e}")
        return None


def delete_file(s3_key: str) -> bool:
    """Delete a file from S3. Returns True on success."""
    client  = get_s3_client()
    bucket  = os.getenv('AWS_STORAGE_BUCKET_NAME')

    try:
        client.delete_object(Bucket=bucket, Key=s3_key)
        logger.info(f"Deleted S3 file: {s3_key}")
        return True

    except ClientError as e:
        logger.error(f"S3 delete failed for {s3_key}: {e}")
        return False


def generate_presigned_url(s3_key: str, expiry_seconds: int = 3600) -> str | None:
    """
    Generate a temporary pre-signed URL for secure resume viewing.
    Default expiry is 1 hour — recruiter can view but not share permanently.
    """
    client  = get_s3_client()
    bucket  = os.getenv('AWS_STORAGE_BUCKET_NAME')

    try:
        url = client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': s3_key},
            ExpiresIn=expiry_seconds,
        )
        return url

    except ClientError as e:
        logger.error(f"Failed to generate presigned URL for {s3_key}: {e}")
        return None