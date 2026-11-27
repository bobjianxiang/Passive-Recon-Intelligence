FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies, curl, unzip, and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    unzip \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download and install OWASP Amass binary (v4.2.0)
RUN curl -sSL https://github.com/owasp-amass/amass/releases/download/v4.2.0/amass_Linux_amd64.zip -o amass.zip \
    && unzip amass.zip \
    && mv amass_Linux_amd64/amass /usr/local/bin/amass \
    && chmod +x /usr/local/bin/amass \
    && rm -rf amass.zip amass_Linux_amd64

# Clone release tag 4.6.0 of theHarvester compatible with Python 3.11
RUN git clone --branch 4.6.0 https://github.com/laramies/theHarvester.git /opt/theHarvester \
    && cd /opt/theHarvester \
    && pip install --no-cache-dir --no-build-isolation . \
    && chmod +x /opt/theHarvester/theHarvester.py \
    && ln -sf /opt/theHarvester/theHarvester.py /usr/local/bin/theHarvester

# Download and install Subfinder binary (v2.6.5)
RUN curl -sSL https://github.com/projectdiscovery/subfinder/releases/download/v2.6.5/subfinder_2.6.5_linux_amd64.zip -o subfinder.zip \
    && unzip subfinder.zip subfinder \
    && mv subfinder /usr/local/bin/subfinder \
    && chmod +x /usr/local/bin/subfinder \
    && rm -rf subfinder.zip

# Download and install Waybackurls binary (v0.1.0)
RUN curl -sSL https://github.com/tomnomnom/waybackurls/releases/download/v0.1.0/waybackurls-linux-amd64-0.1.0.tgz -o waybackurls.tgz \
    && tar -xzf waybackurls.tgz waybackurls \
    && mv waybackurls /usr/local/bin/waybackurls \
    && chmod +x /usr/local/bin/waybackurls \
    && rm -rf waybackurls.tgz

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
