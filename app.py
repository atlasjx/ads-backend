from flask import Flask

app = Flask(__name__)

@app.route("/")
def main():
    return "gha-example"

# ensure the flask app runs only when this script is executed directly
# if it's imported as a module, it won't run
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)