FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace
COPY simulator/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY simulator /workspace/simulator
RUN useradd --create-home app
USER app
CMD ["python", "-m", "simulator.main", "--host", "0.0.0.0"]
