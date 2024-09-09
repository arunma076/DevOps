Create a directory for your Lambda project.

mkdir lambda_project
cd lambda_project


Set Up a Virtual Environment:

python -m venv venv
venv\Scripts\activate


Install prettytable and Dependencies:


pip install boto3 

pip install boto3 dnspython mysql-connector-python

pip install mysql-connector-python



Create Your Lambda Function Code:



Copy the Installed Packages and Your Lambda Function Code:

mkdir deployment_package
xcopy venv\Lib\site-packages\* deployment_package /s /e /y

copy lambda_function.py deployment_package



Create a ZIP Archive:

cd deployment_package
powershell Compress-Archive -Path * -DestinationPath ../lambda_function.zip

cd ..

--------------------------------------------------------------------------------------