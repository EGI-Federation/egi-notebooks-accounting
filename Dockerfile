FROM python:3.15.0

WORKDIR /egi-notebooks-accounting

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN pip install --no-cache-dir .
