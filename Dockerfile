FROM python:3
RUN mkdir /app
WORKDIR /app
COPY requirements.txt /app
RUN pip install -r requirements.txt
COPY billing_report.py /app
COPY pod_exec.py /app
COPY send_email.py /app

