FROM python:3
ADD exporter.py requirements.txt /
RUN pip3 install -r ./requirements.txt
CMD [ "python3", "./exporter.py" ]
