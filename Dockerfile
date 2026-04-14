FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY omega_brain_mcp_standalone.py .
COPY veritas_build_gates.py .

# Non-root user for security
RUN useradd -m omega && chown -R omega:omega /app
USER omega

# Critical for stdio MCP transport — no buffering
ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1

# Default: stdio transport (Glama inspection compatible)
ENTRYPOINT ["python", "omega_brain_mcp_standalone.py"]
