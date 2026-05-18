import requests
from flask import Flask, request, Response, stream_with_context
import os
 
app = Flask(__name__)
 
# --- Configuration ---
# IMPORTANT: Replace with your actual Gemini Enterprise base URL
# This is the URL WITHOUT the dynamic session ID or specific path segments,
# but INCLUDING the google.com/in/home/cid/353-4e92-ad35-47800f9a1c76 part
GEMINI_ENTERPRISE_BASE_URL = os.environ.get(
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
    # Determine the current frontend domain dynamically
    frontend_host = request.host
    frontend_url = f"{request.scheme}://{frontend_host}"

    # Construct the full target URL for Gemini Enterprise
    base_url_stripped = GEMINI_ENTERPRISE_BASE_URL.rstrip("/")
    if path:
        target_url = f"{base_url_stripped}/{path}"
    else:
        target_url = base_url_stripped
        
    if request.query_string:
        target_url += f"?{request.query_string.decode('utf-8')}"
 
    print(f"Proxying request: {request.method} {request.url} -> {target_url}")
 
    # Prepare headers for the request to the backend
    backend_hostname = GEMINI_ENTERPRISE_BASE_URL.replace("https://", "").split("/")[0]
    
    excluded_headers = [
        "host", "connection", "accept-encoding", "if-none-match",
        "x-cloud-trace-context", "traceparent", "x-forwarded-for", 
        "x-forwarded-proto", "x-forwarded-host"
    ]
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in excluded_headers
    }
    headers["Host"] = backend_hostname
    headers["X-Forwarded-For"] = request.remote_addr
 
    # Make the request to the Gemini Enterprise backend
    try:
        resp_from_backend = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            stream=True
        )
    except requests.exceptions.RequestException as e:
        print(f"Error proxying request: {e}")
        return Response(f"Proxy error: {e}", status=500)
 
    # --- Response Rewriting ---
    response_headers = []
    backend_domain = backend_hostname
 
    for key, value in resp_from_backend.headers.items():
        if key.lower() in ["transfer-encoding", "content-encoding", "content-length", "connection"]:
            continue
 
        # Rewrite Location header for redirects
        if key.lower() == "location":
            # Handle both direct and encoded occurrences of the backend URL
            new_location = value.replace(GEMINI_ENTERPRISE_BASE_URL, frontend_url)
            new_location = new_location.replace(backend_domain, frontend_host)
            print(f"Rewriting Location: {value} -> {new_location}")
            response_headers.append((key, new_location))
        # Rewrite Set-Cookie Domain
        elif key.lower() == "set-cookie":
            new_cookie = value.replace(f"domain={backend_domain}", f"domain={frontend_host}")
            new_cookie = new_cookie.replace(backend_domain, frontend_host)
            # Remove 'Secure' flag if testing on http, but Cloud Run is https so it's fine
            response_headers.append((key, new_cookie))
        else:
            response_headers.append((key, value))
 
    # Function to stream and rewrite content
    def generate():
        for chunk in resp_from_backend.iter_content(chunk_size=8192):
            if chunk:
                # Basic string replacement in body
                try:
                    modified_chunk = chunk.decode('utf-8', errors='ignore')
                    modified_chunk = modified_chunk.replace(GEMINI_ENTERPRISE_BASE_URL, frontend_url)
                    modified_chunk = modified_chunk.replace(backend_domain, frontend_host)
                    yield modified_chunk.encode('utf-8')
                except Exception:
                    yield chunk
 
    return Response(
        stream_with_context(generate()),
        status=resp_from_backend.status_code,
        headers=response_headers,
        mimetype=resp_from_backend.headers.get("Content-Type")
    )
 
if __name__ == "__main__":
    # For local testing, use a specified port, e.g., 8080
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
 