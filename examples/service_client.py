"""A runnable HTTP integration with no third-party Python dependencies.

Set SURVEY_MACHINE_URL to the service origin (or mounted base URL), and
SURVEY_MACHINE_KEY to a server-side integration key. Running this file creates a
demo survey and a demo response in that key's workspace.
"""

import json
import os
from urllib.request import Request, urlopen
from uuid import uuid4


class SurveyClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url.rstrip("/") + "/api/v1"
        self.api_key = api_key

    def request(self, method, path, body=None, *, public=False):
        headers = {} if public else {"X-API-Key": self.api_key}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, method=method, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        with urlopen(request, timeout=30) as response:
            return json.load(response)


def demo(client):
    survey = client.request("POST", "/surveys", {
        "title": "An embedded feedback example", "respondent_mode": "anonymous",
        "questions": [{"type": "rating", "title": "How was your experience?", "required": True}],
    })
    client.request("POST", f"/surveys/{survey['id']}/publish")
    token = survey["public_path"].split("/")[-1]
    form = client.request("GET", f"/public/surveys/{token}", public=True)
    # In your app, render these questions and collect the respondent's answers.
    # Keep this UUID when retrying this particular submission after network errors.
    submission = {"submission_id": str(uuid4()), "answers": {form["questions"][0]["id"]: 5}}
    client.request("POST", f"/public/surveys/{token}/responses", submission, public=True)
    summary = client.request("GET", f"/surveys/{survey['id']}/summary")
    return {"survey_id": survey["id"], "responses": summary["total"]}


if __name__ == "__main__":
    print(json.dumps(demo(SurveyClient(os.environ["SURVEY_MACHINE_URL"], os.environ["SURVEY_MACHINE_KEY"]))))
