__author__ = "Ivan Gushchin"
__copyright__ = ""
__credits__ = [""]
__license__ = "GPL"
__version__ = "0.0.1"
__maintainer__ = "Ivan Gushchin"
__email__ = "mug0ft10@gmail.com"

import zipfile
import os
import sqlite3
import json
import urllib
import boto3

from bs4 import BeautifulSoup
from pathlib import Path
from botocore import exceptions

from models import note

# If This file name is not found after extraction -> apkg file is invalid
ANKI_FILE_NAME_EXPECTED_IN_EACH_APKG = "collection.anki2"

DEFAULT_REGION = 'eu-central-1'
AWS_REGION = os.environ.get('AWS_REGION', DEFAULT_REGION)
TABLE_NAME_NOTES_DEFAULT = "notes"
TABLE_NAME_NOTES = os.environ.get('TABLE_NAME_NOTES', TABLE_NAME_NOTES_DEFAULT)
TABLE_NAME_NOTES_STATUS_DEFAULT = "notes_status"
TABLE_NAME_NOTES_STATUS = os.environ.get('TABLE_NAME_NOTES_STATUS', TABLE_NAME_NOTES_STATUS_DEFAULT)

CHAT_ID_CHANNEL_QUESTIONS_DEFAULT = 1001566093710
CHAT_ID_CHANNEL_QUESTIONS = os.environ.get('CHAT_ID_CHANNEL_QUESTIONS', CHAT_ID_CHANNEL_QUESTIONS_DEFAULT)


def handler(event, context):
    print("Received event: " + json.dumps(event))

    folder_out = '/tmp'
    anki_local_file_path = download_file(event, folder_out)

    notes = []
    extract_notes_from_apkg(anki_local_file_path, folder_out, notes)

    add_notes_to_dynamo_db(notes)

    print("Success")
    return {'Message': 'SUCCESS', 'StatusCode': 200}


def download_file(event, folder_out):
    se3_client = boto3.client('s3', region_name=AWS_REGION)
    # Get the object from the event and show its content type
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')
    anki_local_file_path = os.path.join(folder_out, key)
    print("Bucket: " + bucket)
    print("Key: " + key)
    try:
        se3_client.download_file(Bucket=bucket, Key=key, Filename=anki_local_file_path)
    except Exception as e:
        print(e)
        print(
            'Error  getting object {} from bucket {}. Make sure they exist and your bucket is in the same region as this function.'.format(
                key, bucket))
        raise e
    return anki_local_file_path


def extract_notes_from_apkg(anki_local_file_path, tmp_folder_path, notes):
    if Path(anki_local_file_path).is_file():
        print("Processing apkg file " + anki_local_file_path)

    # unzip anki SQL Lite file
    with zipfile.ZipFile(anki_local_file_path, "r") as zip_ref:
        zip_ref.extractall(tmp_folder_path)

    ankiFileExtracted = Path(os.path.join(tmp_folder_path, ANKI_FILE_NAME_EXPECTED_IN_EACH_APKG))

    if not ankiFileExtracted.is_file():
        print("File " + str(ankiFileExtracted.absolute()) + " doesn't exist")
        os.sys.exit(1)

    # connect to SQL Lite DB file
    con = sqlite3.connect(str(ankiFileExtracted.absolute()))
    cur = con.cursor()
    cur.execute("SELECT id AS note_id, mod AS mod, flds AS flds FROM notes")
    rows = cur.fetchall()
    print("Extracting notes from " + str(ankiFileExtracted.absolute()))
    for row in rows:
        question_answer = str(row[2]).split("")

        # TODO: play around the code below to preserve allowed tags and attributes (like <b></b> (bold) and etc. See page for allowed tags: https://core.telegram.org/bots/api#available-methods
        # You need bleach to be installed
        # question = "<div><div>(EN)</div>What is <b>linked</b> list and double linked list? Please name cons and pros of the linked list in comparison to the similar kind of structures. Please specify the complexity.<div><br></div><div>(RU)</div><div>Что такое связный список? Чем отличается односвязный список от двусвязного? Назови преимущества и недостатки связного списка по отношению к другим подобным структурам. Назови сложность связного списка.</div></div>"
        # questionSoup = BeautifulSoup(question, "lxml")
        # container = questionSoup.find('div')
        # keep = []
        # for node in container.descendants:
        #     if not node.name or node.name == 'b' or node.name == 'div':
        #         keep.append(node)

        question = question_answer[0]
        # remove html symbols
        question = BeautifulSoup(question, "html.parser").getText(separator="\n")

        answer = question_answer[1]
        # remove html symbols
        answer = BeautifulSoup(answer, "html.parser").get_text(separator="\n")
        # answer2 =  strip_html(answer)
        _note = note.Note(int(row[0]), int(row[1]), question, answer)
        print("Note with id " + str(_note.get_note_id()) + " has been successfully extracted")
        notes.append(_note)
    cur.close()


def add_notes_to_dynamo_db(notes):
    print("Adding notes to table " + TABLE_NAME_NOTES)
    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    table = dynamodb.Table(TABLE_NAME_NOTES)
    # TODO: batch writer doesn't support ConditionExpression.
    #  later we should use batch anyway
    # with table.batch_writer() as batch:
    for note in notes:
        try:
            table.put_item(
                Item={
                    'note_id': note.get_note_id(),
                    'mod': note.get_mod(),
                    'question': note.get_question(),
                    'answer': note.get_answer(),
                },
                ConditionExpression='attribute_not_exists(note_id)'
            )
        except exceptions.ClientError as e:
            # Ignore the ConditionalCheckFailedException, bubble up
            # other exceptions.
            if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
                raise
    print("Updating table " + TABLE_NAME_NOTES_STATUS)
    table = dynamodb.Table(TABLE_NAME_NOTES_STATUS)
    # with table.batch_writer() as batch:
    for note in notes:
        try:
            table.put_item(
                Item={
                    'chat_id': CHAT_ID_CHANNEL_QUESTIONS,
                    'note_id': note.get_note_id(),
                    'last_asked_time': 0,
                },
                ConditionExpression='attribute_not_exists(chat_id) AND attribute_not_exists(note_id)'
            )
        except exceptions.ClientError as e:
            # Ignore the ConditionalCheckFailedException, bubble up
            # other exceptions.
            if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
                raise
