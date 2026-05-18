import requests
from flask import Flask, request, Response, stream_with_context
import os
 
app = Flask(__name__)
 
# --- Configuration ---
# IMPORTANT: Replace with your actual Gemini Enterprise base URL
# This is the URL WITHOUT the dynamic session ID or specific path segments,
# but INCLUDING the google.com/in/home/cid/353-4e92-ad35-47800f9a1c76 part
BASE_URL = os.environ.get(
    "GEMINI_ENTERPRISE_BASE_URL",
    "https://vertexaisearch.cloud.google/in/home/cid/f60333c4-d353-4e92-ad35-47800f9a1c76"
)
 
# Your desired custom domain (e.g., abc.com)
CUSTOM_FRONTEND_DOMAIN = os.environ.get(
    "CUSTOM_FRONTEND_DOMAIN",
    "abc.com"
)
 
# --- Proxy Logic ---
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
def proxy(path):
    # Construct the full target URL for Gemini Enterprise
    # The Load Balancer (later) will handle prepending the /in/home/cid... segment
    # For now, Cloud Run will receive requests that *already* have this path component
    # if you route directly or via a Load Balancer that does not strip it.
    # We will assume the full path is being sent to Cloud Run for the internal request.
    target_url = f"{GEMINI_ENTERPRISE_BASE_URL}/{path}"
 
    print(f"Proxying request: {request.method} {request.url} -> {target_url}")
 
    # Prepare headers for the request to the backend
    # Remove headers that might cause issues or are specific to the client connection
    excluded_headers = [
        "host", "connection", "accept-encoding", "if-none-match",
        "x-cloud-trace-context", "traceparent", "user-agent" # User-agent can be passed if desired
    ]
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in excluded_headers
    }
 
    # Add X-Forwarded-* headers (standard for proxies)
    headers["X-Forwarded-For"] = request.remote_addr
    headers["X-Forwarded-Proto"] = request.scheme
    headers["X-Forwarded-Host"] = request.host
 
    # Make the request to the Gemini Enterprise backend
    try:
        resp_from_backend = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(), # Use get_data() for raw body
            cookies=request.cookies,
            allow_redirects=False, # Crucial for manual Location header rewriting
            stream=True # Stream the response for efficiency
        )
    except requests.exceptions.RequestException as e:
        print(f"Error proxying request: {e}")
        return Response(f"Proxy error: {e}", status=500)
 
    # --- Response Rewriting ---
    # Prepare response headers for the client
    response_headers = []
    full_backend_prefix_to_replace = GEMINI_ENTERPRISE_BASE_URL.replace("https://", "")
 
    for key, value in resp_from_backend.headers.items():
        # Exclude headers that might interfere or are backend-specific
        if key.lower() in ["transfer-encoding", "content-encoding", "content-length", "connection"]:
            continue
 
        # Rewrite Location header for redirects
        if key.lower() == "location":
            new_location = value.replace(GEMINI_ENTERPRISE_BASE_URL, f"https://{CUSTOM_FRONTEND_DOMAIN}")
            print(f"Rewriting Location: {value} -> {new_location}")
            response_headers.append((key, new_location))
        # Rewrite Set-Cookie Domain
        elif key.lower() == "set-cookie":
            # Attempt to replace the domain in the cookie
            new_cookie = value.replace(full_backend_prefix_to_replace.split('/')[0], CUSTOM_FRONTEND_DOMAIN)
            print(f"Rewriting Set-Cookie domain: {value} -> {new_cookie}")
            response_headers.append((key, new_cookie))
        else:
            response_headers.append((key, value))
 
    # Function to stream and rewrite content
    def generate():
        for chunk in resp_from_backend.iter_content(chunk_size=8192):
            if chunk:
                # This is a very basic rewrite for content.
                # For complex JS/HTML that dynamically generates URLs,
                # you might need a more sophisticated parser or regex.
                # However, for simple string replacement in body, this works.
                modified_chunk = chunk.decode('utf-8', errors='ignore')
                modified_chunk = modified_chunk.replace(GEMINI_ENTERPRISE_BASE_URL, f"https://{CUSTOM_FRONTEND_DOMAIN}")
                yield modified_chunk.encode('utf-8')
 
    return Response(
        stream_with_context(generate()),
        status=resp_from_backend.status_code,
        headers=response_headers,
        mimetype=resp_from_backend.headers.get("Content-Type")
    )
 
if __name__ == "__main__":
    # For local testing, use a specified port, e.g., 8080
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
 