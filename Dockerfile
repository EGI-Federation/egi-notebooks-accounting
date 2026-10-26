FROM python:3.13.17-slim

WORKDIR /egi-notebooks-accounting

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN ls -a && git status
RUN pip install --no-cache-dir .
