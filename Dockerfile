# Use the official Python image as a parent image.
# We recommend a specific version to ensure consistency.
FROM python:3.9-slim-buster
 
# Set the working directory in the container.
WORKDIR /app
 
# Install production dependencies.
# Copy requirements.txt first to leverage Docker's layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
 
# Copy the rest of your application code.
COPY . .
 
# Expose the port that the application will listen on.
# Cloud Run automatically sets the PORT environment variable.
ENV PORT 8080
EXPOSE $PORT
 
# Run the application using Gunicorn.
# Using the shell form of CMD to ensure $PORT is expanded correctly.
CMD gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app