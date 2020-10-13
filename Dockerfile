FROM python:3.8.6-alpine
RUN apk add --update --upgrade gcc musl-dev
ADD exporter.py requirements.txt /
RUN pip3 install -r ./requirements.txt
ENTRYPOINT [ "python3", "./exporter.py" ]
