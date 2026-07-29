from flask import Flask
import urllib.request

app = Flask(__name__)

@app.route("/")
def test():
    url = "https://in.bookmyshow.com/HYD/venue-list"

    try:
        response = urllib.request.urlopen(url, timeout=20)

        data = response.read(500)

        return {
            "status": response.status,
            "content": data.decode("utf-8", errors="ignore")
        }

    except Exception as e:
        return {
            "error": repr(e)
        }, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
