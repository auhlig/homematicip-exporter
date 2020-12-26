FROM python:3.8.6-slim-buster
ADD exporter.py requirements.txt /
RUN pip3 install -r ./requirements.txt
ENTRYPOINT [ "python3", "./exporter.py" ]
