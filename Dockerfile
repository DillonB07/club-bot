# Use the official Python image as the base image
FROM python:3.11.7-alpine3.19

# Set the working directory in the container
WORKDIR /app

# Copy the poetry.lock and pyproject.toml files to the container
COPY poetry.lock pyproject.toml /app/

# Install poetry
RUN pip install poetry==1.5.1

# Install project dependencies using poetry
RUN poetry install --no-root --no-dev

# Copy the rest of the project files to the container
COPY . /app

VOLUME /app/clubs.csv

# Run main.py
CMD ["python", "main.py"]
