FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace

# Microsoft ODBC Driver 18 for Debian 12.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates unixodbc libgssapi-krb5-2 \
    && curl -fsSLo /tmp/packages-microsoft-prod.deb https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/* /tmp/packages-microsoft-prod.deb

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY services ./services
COPY shared ./shared
COPY frontend ./frontend
COPY infra ./infra

RUN useradd --create-home serviceuser
USER serviceuser
CMD ["python", "-m", "uvicorn", "services.account.main:app", "--host", "0.0.0.0", "--port", "8001"]
