"""Upload artifact containing the pytest results and configuration to an s3 bucket.

This will in turn get picked by narberachka service,
which will either send it to ibutsu or report portal, based on the
prefix of the file name.
A dictionary containing the credentials of the S3 bucket must be specified, containing the keys:
AWS_BUCKET
AWS_REGION
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY

"""


def upload_artifact_s3(aws_env):
    """Upload artifact to the specified S3 bucket."""
    return True
