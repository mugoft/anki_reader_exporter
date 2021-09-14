import os
import tempfile
import unittest
import importlib.resources
from unittest import mock

import boto3

from processor import lambda_handler
from moto import mock_s3, mock_dynamodb2

from processor.lambda_handler import download_file, DEFAULT_REGION, TABLE_NAME_NOTES_STATUS_DEFAULT, \
    TABLE_NAME_NOTES_DEFAULT, TABLE_NAME_NOTES, TABLE_NAME_NOTES_STATUS, AWS_REGION
from processor.models import note

S3_TEST_BUCKET = 'sam-anki-reader-exporter-testbucket'
S3_TEST_KEY = 'Computing__SWD.apkg'
S3_TEST_EVENT = {
    'Records': [
        {
            's3': {
                'bucket': {
                    'name': S3_TEST_BUCKET
                },
                'object': {
                    'key': S3_TEST_KEY
                }
            }
        }
    ]
}


@mock_s3
@mock_dynamodb2
@mock.patch.dict(os.environ, {'TABLE_NAME_NOTES_STATUS': TABLE_NAME_NOTES_STATUS_DEFAULT,
                              'TABLE_NAME_NOTES': TABLE_NAME_NOTES_DEFAULT})
class MyTestCase(unittest.TestCase):

    def setUp(self):
        """Mocked AWS Credentials for moto."""
        boto3.setup_default_session()
        self.s3 = boto3.resource('s3', region_name=AWS_REGION)
        # We need to create the bucket since this is all in Moto's 'virtual' AWS account

        self.s3_bucket = self.s3.create_bucket(Bucket=S3_TEST_BUCKET,
                                               CreateBucketConfiguration={'LocationConstraint': AWS_REGION})
        anki_cards_path = ""
        with importlib.resources.path("tests.resources", S3_TEST_KEY) as p:
            anki_cards_path = str(p)
        self.s3_bucket.upload_file(anki_cards_path, S3_TEST_KEY)

        # DynamoDB setup
        self.dynamodb = boto3.client('dynamodb', region_name=AWS_REGION)
        try:
            self.table_notes = self.dynamodb.create_table(
                TableName=TABLE_NAME_NOTES,
                KeySchema=[
                    {'AttributeName': 'note_id', 'KeyType': 'HASH'},
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'note_id', 'AttributeType': 'N'}
                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            )

        except self.dynamodb.exceptions.ResourceInUseException:
            self.table_notes = boto3.resource('dynamodb', region_name=AWS_REGION).Table(TABLE_NAME_NOTES)

        try:
            self.table_notes_status = self.dynamodb.create_table(
                TableName=TABLE_NAME_NOTES_STATUS,
                KeySchema=[
                    {'AttributeName': 'note_id', 'KeyType': 'HASH'},
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'note_id', 'AttributeType': 'N'}
                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            )
        except self.dynamodb.exceptions.ResourceInUseException:
            self.table_notes_status = boto3.resource('dynamodb', region_name=AWS_REGION).Table(TABLE_NAME_NOTES_STATUS)

    def test_download_apkg(self):
        with tempfile.TemporaryDirectory() as tmp_folder_path:
            downloaded_file_path = download_file(S3_TEST_EVENT, tmp_folder_path)
            self.assertTrue(os.path.isfile(downloaded_file_path))

    def test_extract_notes_from_apkg(self):
        notes_len_expected = 21
        id_expected = 1631784702480
        question_expected = "What is CAP theorem?"
        answer_expected_start = 'In theoretical computer science, the CAP theorem,'

        with tempfile.TemporaryDirectory() as tmp_folder_path:
            with importlib.resources.path("tests.resources", "Computing__SWD.apkg") as p:
                anki_cards_path = str(p)

            notes = []
            lambda_handler.extract_notes_from_apkg(anki_cards_path, tmp_folder_path, notes)
            self.assertEqual(len(notes), notes_len_expected)
            note_expected = next((_note for _note in notes if _note.get_note_id() == id_expected), None)
            self.assertIsNotNone(note_expected)
            self.assertEqual(note_expected.get_question(), question_expected)
            self.assertTrue(note_expected.get_answer().startswith(answer_expected_start))

    def test_add_notes_to_dynamo_db(self):
        notes = [note.Note(int(1631787514816), 1631787514, "Question", "Answer")]
        lambda_handler.add_notes_to_dynamo_db(notes)
        print(self.table_notes)
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(TABLE_NAME_NOTES)
        response = table.get_item(Key={'note_id': 1631787514816})
        item = response['Item']

        self.assertEqual(item['note_id'], 1631787514816)
        self.assertEqual(item['question'], "Question")
        self.assertEqual(item['answer'], "Answer")

    def test_handler(self):
        result = lambda_handler.handler(S3_TEST_EVENT, {})
        self.assertEqual(result, {'StatusCode': 200, 'Message': 'SUCCESS'})


if __name__ == '__main__':
    unittest.main()
