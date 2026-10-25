FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY app ./app
COPY .streamlit ./.streamlit
RUN pip install --no-cache-dir -e ".[app]"
EXPOSE 8501
CMD ["streamlit", "run", "app/Home.py", "--server.address=0.0.0.0", "--server.port=8501"]
