import requests

def test_server(text):
    # API endpoint URL
    url = "http://127.0.0.1:8000/predict"
    # Request payload
    payload = {"text": text}
    # POST request to the server
    response = requests.post(url, json=payload)
    # Print the response from the server
    print(response.json())

if __name__ == "__main__":
    sample_text = "I love machine learning. My experience with LitServe has been amazing!"
    test_server(sample_text)