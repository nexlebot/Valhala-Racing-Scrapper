# Vahala Racing Scraper

AWS Lambda scraper that collects trainer race data and horse profiles from RaceNet and pushes them to the Vahala Racing Next.js site.

## What it does

- Scrapes upcoming races, major wins, and previous runners for trainer Stefan Vahala from [RaceNet](https://www.racenet.com.au/profiles/trainer/stefan-vahala)
- Fetches horse profiles and career stats from the Racing WA API
- Pushes all data to the Next.js API at `vahala-racing.netlify.app`

## Stack

- Python 3.11
- Selenium + Chrome (headless)
- BeautifulSoup4
- AWS Lambda (Docker container)
- EventBridge (scheduled trigger)

## Deployment

### Prerequisites
- Docker
- AWS CLI configured
- ECR repository: `vahala-scrapper`

### Build & Deploy

```bash
# Build image
docker build --platform linux/amd64 -t vahala-scrapper .

# Push to ECR
docker tag vahala-scrapper <account>.dkr.ecr.ap-southeast-2.amazonaws.com/vahala-scrapper:latest
aws ecr get-login-password --region ap-southeast-2 | docker login --username AWS --password-stdin <account>.dkr.ecr.ap-southeast-2.amazonaws.com
docker push <account>.dkr.ecr.ap-southeast-2.amazonaws.com/vahala-scrapper:latest

# Update Lambda
aws lambda update-function-code \
  --function-name vahala-scrapper-docker \
  --image-uri <account>.dkr.ecr.ap-southeast-2.amazonaws.com/vahala-scrapper:latest \
  --region ap-southeast-2
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `NEXTJS_BASE_URL` | Base URL of the Next.js site |
| `SCRAPER_TOKEN` | Bearer token for the Next.js API |

## Schedule

Runs daily at **4am Sydney time** via EventBridge (`cron(0 17 * * ? *)`).

## Local Development

```bash
pip install -r requirements.txt
cp .env.example .env  # fill in values
python racenet_scrapper.py
```

## Lambda Config

- Memory: 1024 MB
- Timeout: 10 minutes
- Architecture: x86_64
- Runtime: Docker (Python 3.11)
