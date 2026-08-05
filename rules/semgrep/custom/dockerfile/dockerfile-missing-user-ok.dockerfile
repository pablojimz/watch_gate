# ok: dockerfile-missing-user
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y python3
RUN useradd -m appuser
USER appuser
COPY . /app
CMD ["python3", "/app/main.py"]
