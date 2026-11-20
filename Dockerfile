# Peek - Docker image for LINUX hosts (home server, Raspberry Pi, NAS, VPS).
#
# What works in Docker: CPU/RAM/disk/network charts, watched processes, reboot/wake events,
# push notifications, login.  What does NOT: screenshots, lock screen, idle detection -
# a container has no desktop session. On Windows and macOS, Docker runs inside a Linux VM
# and can't see your computer at all, so use setup.bat / setup.sh there instead.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PCG_DATA_DIR=/data \
    PCG_HOST=127.0.0.1 \
    PCG_PORT=8765

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY guardian.py .
COPY pcguardian ./pcguardian
COPY static ./static

VOLUME ["/data"]
EXPOSE 8765
CMD ["python", "guardian.py"]
