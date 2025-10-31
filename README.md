# gha-example
Example of a simple app to test GitHub Actions.

## Running
Get into the virtual environment:  
source venv/bin/activate

In development:  
python3 app.py

Docker build & run:  
docker build -t gha-example .  
docker run -p 5000:5000 gha-example