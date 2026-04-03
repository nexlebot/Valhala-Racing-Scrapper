FROM python:3.11-slim-bookworm

RUN pip install awslambdaric --no-cache-dir

ENV LAMBDA_TASK_ROOT=/var/task
ENV LAMBDA_RUNTIME_DIR=/var/runtime
RUN mkdir -p ${LAMBDA_TASK_ROOT}

RUN apt-get update && apt-get install -y \
    wget unzip libatk1.0-0 libatk-bridge2.0-0 libcups2 libxcomposite1 \
    libxcursor1 libxdamage1 libxext6 libxi6 libxrandr2 libxss1 libxtst6 \
    libpango-1.0-0 libnss3 libgbm1 libasound2 libxkbcommon0 libgtk-3-0 \
    fonts-liberation --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

RUN wget -q https://storage.googleapis.com/chrome-for-testing-public/143.0.7499.192/linux64/chrome-linux64.zip && \
    unzip -q chrome-linux64.zip && \
    mv chrome-linux64 /opt/chrome && \
    rm chrome-linux64.zip

RUN wget -q https://storage.googleapis.com/chrome-for-testing-public/143.0.7499.192/linux64/chromedriver-linux64.zip && \
    unzip -q chromedriver-linux64.zip && \
    mv chromedriver-linux64/chromedriver /opt/chromedriver && \
    chmod +x /opt/chromedriver && \
    rm -rf chromedriver-linux64 chromedriver-linux64.zip

WORKDIR ${LAMBDA_TASK_ROOT}

COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir

COPY racenet_scrapper.py .

ENTRYPOINT ["/usr/local/bin/python", "-m", "awslambdaric"]
CMD ["racenet_scrapper.lambda_handler"]
