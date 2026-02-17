# Use official Playwright image (includes browsers + deps)
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /code

COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /code

# Optional: for faster logs
ENV PYTHONUNBUFFERED=1
