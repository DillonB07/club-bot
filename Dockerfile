# Use the official Python image as the base image
FROM python:3.11.7-alpine3.19

# Set label
LABEL org.opencontainers.image.source="https://github.com/DillonB07/Club-Bot"

# Set the working directory in the container
WORKDIR /app

# Copy the poetry.lock and pyproject.toml files to the container
COPY poetry.lock pyproject.toml /app/

# Install poetry and add to PATH
RUN apk add --no-cache curl && \
    curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="~/.local/bin:$PATH"

# Install project dependencies using poetry
RUN poetry install --no-root --no-dev

# Copy the rest of the project files to the container
COPY . /app

# Run main.py
CMD ["poetry", "run", "python", "main.py"]
