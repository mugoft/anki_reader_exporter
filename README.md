# anki_reader_exporter
Python project which downloads Anki APKG files from AWS S3 input bucket, unzips them, extracts notes from the unzipped files, and pushes these notes into AWS DynamoDB.

The project is configured to be built and deployed using Github Actions and AWS SAM.

After successful build and deployment, the following resources are created by CloudFormation stack:
- Lambda: contains Python code for processing APKG file
  - Lambda Layer: contains dependencies needed for reading and cleaning APKG files. 
- S3 Bucket: contains APKG files, and used as a trigger for Lambda - whenever new APKG file is created, lambda receives event with the name of newly created APKG file, and starts processing this file.

