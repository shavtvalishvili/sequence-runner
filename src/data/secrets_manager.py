import json
import os

import boto3
from botocore.exceptions import ClientError


class SecretsManager:
    def __init__(self):
        self.secrets = {}
        self._import_all_secrets()

    def _import_all_secrets(self):
        secret_name = f"{os.getenv("ENV")}/agent-platform-sequence-runner"
        region_name = os.getenv("AWS_DEFAULT_REGION")

        session = boto3.session.Session()
        client = session.client(
            service_name='secretsmanager',
            region_name=region_name
        )

        try:
            get_secret_value_response = client.get_secret_value(
                SecretId=secret_name
            )
        except ClientError as e:
            raise e

        secret_values = json.loads(get_secret_value_response['SecretString'])
        self.secrets.update(secret_values)

    def update_env_with_secrets(self):
        os.environ.update(self.secrets)

    def get_secret(self, secret_name):
        if secret_name not in self.secrets:
            raise ValueError(f"Secret {secret_name} not found.")
        return self.secrets[secret_name]