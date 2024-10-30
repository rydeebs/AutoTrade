from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def hello():
    return 'Trading Bot is running!'

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    app.run()