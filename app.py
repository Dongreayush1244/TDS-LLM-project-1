import os, base64, requests, uuid
from fastapi import FastAPI, Request
from dotenv import load_dotenv
import re
load_dotenv()

app = FastAPI(title="LLM Code Deployment API")

AIPIPE_TOKEN = os.getenv("AIPIPE_TOKEN")
STUDENT_SECRET = os.getenv("STUDENT_SECRET")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
PORT = int(os.getenv("PORT", 3000))

AIPIPE_API_URL = "https://aipipe.org/openrouter/v1/chat/completions"


@app.get("/")
def root():
    return {"status": "ok", "message": "LLM Code Deployment API active"}

@app.post("/api-endpoint")
async def receive_task(request: Request):
    data = await request.json()
    print("Received task:", data)

    if data.get("secret") != STUDENT_SECRET:
        return {"status": "error", "message": "Invalid secret"}

    brief = data.get("brief", "")
    task_id = data.get("task", f"auto-{uuid.uuid4().hex[:8]}")
    round_no = data.get("round", 1)
    nonce = data.get("nonce", "")

    headers = {
            "Authorization": f"Bearer {AIPIPE_TOKEN}",
            "Content-Type": "application/json"
        }
    payload = {
            "model": "openai/gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are an expert AI code generator."},
                {"role": "user", "content": f"Generate only code no text other than that for this task:\n{brief}"}
            ]
        }

    print("Sending request to AIPipe...")
    llm_resp = requests.post(AIPIPE_API_URL, headers=headers, json=payload, timeout=60)
    print("AIPipe status:", llm_resp.status_code)
    result = llm_resp.json()
    full_output = result["choices"][0]["message"]["content"]
    match = re.search(r"```(?:\w*\n)?([\s\S]*?)```", full_output)
    if match:
        code_output = match.group(1).strip()
    else:
        code_output = full_output.strip()

    repo_name = task_id.replace("_", "-")
    create_repo = requests.post(
        "https://api.github.com/user/repos",
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
        json={"name": repo_name, "auto_init": True, "private": False, "description": brief}
    )

    if create_repo.status_code != 201:
        return {"status": "error", "message": f"GitHub repo creation failed: {create_repo.text}"}

    content_b64 = base64.b64encode(code_output.encode()).decode()
    upload_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/contents/index.html"
    requests.put(
        upload_url,
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
        json={"message": "Add index.html", "content": content_b64}
    )

    license_text = """MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files..."""
    license_b64 = base64.b64encode(license_text.encode()).decode()
    license_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/contents/LICENSE"
    requests.put(
        license_url,
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
        json={"message": "Add LICENSE", "content": license_b64}
    )

    requests.post(
        f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/pages",
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
        json={"source": {"branch": "main"}}
    )

    repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}"
    pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"

    evaluation_url = data.get("evaluation_url")
    if evaluation_url:
        payload = {
            "email": data.get("email"),
            "task": task_id,
            "round": round_no,
            "nonce": nonce,
            "repo_url": repo_url,
            "commit_sha": "latest",
            "pages_url": pages_url,
        }

        try:
            eval_resp = requests.post(evaluation_url, json=payload, timeout=10)
            print(" Evaluation POST →", eval_resp.status_code)
        except Exception as e:
            print("Evaluation POST failed:", e)

    return {
        "status": "ok",
        "task": task_id,
        "round": round_no,
        "repo_url": repo_url,
        "pages_url": pages_url,
        "message": "App deployed successfully!"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)

