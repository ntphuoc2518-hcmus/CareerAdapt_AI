# Image for running learners' SQL and Python in a container (CAREERADAPT_SANDBOX=docker).
#
# Build once on the server, from the project folder:
#     docker build -t careeradapt-sandbox:1 sandbox
#
# The image holds only Python and the three libraries the exam allows. The worker scripts are not copied
# in: each run mounts backend/engine read-only, so the image never has to be rebuilt when they change.
# Runs are started by backend/engine/container_sandbox.py with no network, a read-only root filesystem,
# memory/CPU/process limits, no Linux capabilities and the unprivileged user 65534.
FROM python:3.13-slim

# Same versions as requirements.txt, so code behaves the same as in the local sandbox.
RUN pip install --no-cache-dir pandas==2.3.3 numpy==2.3.4 matplotlib==3.10.7 \
    && python -c "import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot"

ENV MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /work
USER 65534:65534
