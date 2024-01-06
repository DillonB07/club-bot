# Use the official Python image as the base image
FROM fnndsc/python-poetry

# Set label
LABEL org.opencontainers.image.source="https://github.com/DillonB07/Club-Bot"

# Set the working directory in the container
WORKDIR /app

# Copy the poetry.lock and pyproject.toml files to the container
COPY poetry.lock pyproject.toml /app/

# Install build tools
USER root
RUN apt update && apt install -y --no-install-recommends \
    gcc \
    libc6-dev
USER mambauser

# Install project dependencies using poetry
RUN poetry install --only main 

# Copy the rest of the project files to the container
COPY . /app

# Run main.py
CMD ["poetry", "run", "python", "main.py"]
