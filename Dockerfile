FROM python:3.6-alpine

# To reduce build times when developing/uploading
RUN apk add build-base && pip install Flask==2.1.0 pyOpenSSL==22.1.0 dydx-v3-python==1.9.0

WORKDIR /app
COPY . .
# RUN pip install -r requirements.txt

CMD ["python3","-u","/app/run.py"]
