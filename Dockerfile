FROM python:3.12

COPY . /app
WORKDIR /app
RUN rm -r env

RUN pip install -r requirements.txt

CMD ["python", "./main.py"]