# Integrating with Survey Machine

Base URL: https://YOUR_HOST/api/v1. Local default: http://127.0.0.1:8000/api/v1.
The interactive reference is at /docs and the OpenAPI schema is at /openapi.json.

HTTP and JSON make the same API usable from Java, Python, PHP, C, JavaScript and
other languages. Host your own UI or copy an iframe from the application's Share
dialog. The UI and integrations use the same API and data.

To run the API within your own infrastructure, see [self-hosting and Python embedding](self-hosting.md).
An independent installation does not require an account on the hosted service.

## Authentication and account scope

A customer signs in to the browser app and creates a key under **Integrations**.
Send that key in X-API-Key from the integrating application's server.

| Permission | Operations |
| --- | --- |
| surveys:read | List/read surveys |
| surveys:write | Create/edit/duplicate/publish/close surveys |
| responses:read | Read responses, summaries, CSV and JSON exports |
| responses:delete | Delete individual responses |
| surveys:write + responses:delete | Delete a survey and all its responses |

Keys are bound to the customer's workspace, displayed once, stored as digests and
individually revocable. They cannot create other keys, invite customers or switch
workspaces. Never ship private keys in frontend JavaScript, mobile binaries, public
URLs, or iframe attributes. Use public survey endpoints for respondents.

The service operator's ADMIN_API_KEY is more privileged and is for administration,
not customer integrations.

## Survey lifecycle

| Method | Path relative to /api/v1 | Behavior |
| --- | --- | --- |
| GET | /surveys | List; limit 1–100, offset, status, search |
| POST | /surveys | Create a draft |
| GET | /surveys/{id} | Read a private survey definition |
| PUT | /surveys/{id} | Replace a draft; include its current revision |
| POST | /surveys/{id}/publish | Publish or reopen |
| POST | /surveys/{id}/close | Stop accepting responses |
| POST | /surveys/{id}/duplicate | Create an editable draft copy |
| DELETE | /surveys/{id} | Delete survey and responses |

Create a survey:

~~~sh
curl "$SURVEY_MACHINE_URL/api/v1/surveys" \
  -H "X-API-Key: $SURVEY_MACHINE_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"title":"Quick feedback","respondent_mode":"anonymous","questions":[{"type":"short_text","title":"What could we improve?","required":true}]}'
~~~

The response includes id, questions with UUID IDs, revision and public_path.
Publish using POST /surveys/{id}/publish, then share YOUR_HOST + public_path.
A published definition is locked; duplicate it when changing questions.

Question types are short_text, long_text, email, number, date, single_choice,
multiple_choice and rating. Choice questions require 2–30 distinct options.
Ratings start at 1 and end at an integer from 3 to 10. Number bounds are optional.
A survey supports up to 50 questions; descriptions and other field limits appear
in OpenAPI and are checked on the server.

## Collecting public responses

GET /public/surveys/{token} returns title, description, respondent mode and questions.
POST /public/surveys/{token}/responses accepts:

~~~json
{
  "submission_id": "11111111-1111-4111-8111-111111111111",
  "answers": {
    "REPLACE_WITH_QUESTION_UUID": "Clearer appointment reminders"
  }
}
~~~

Use a fresh random UUID per intended response. Keep it for retries. Repeating an
identical submission returns the same receipt; changing the answers for that ID
returns 409. Do not use the example UUID repeatedly in a real client.

Named surveys also require respondent_name. Anonymous surveys reject that field.
Numbers/ratings must be JSON numbers; multiple-choice answers are arrays of option
strings; dates use YYYY-MM-DD. Names are self-reported, not identity verification.

Public share tokens are bearer links. Anyone possessing one can respond while the
survey is open. Idempotency prevents accidental network retries; it is not
one-response-per-person enforcement or a bot-detection system.

## Reviewing results

| Method | Path | Behavior |
| --- | --- | --- |
| GET | /surveys/{id}/responses | Paginated responses |
| GET | /surveys/{id}/summary | Answer counts, choice counts, numeric/rating averages |
| GET | /surveys/{id}/export?format=csv | CSV download |
| GET | /surveys/{id}/export?format=json | JSON download |
| DELETE | /surveys/{id}/responses/{response_id} | Remove one response |

Anonymous records omit respondent_name. CSV output includes question UUIDs in its
column headers and prefixes formula-like text to protect spreadsheet imports.
JSON preserves the original cleaned answer values.

## Client examples

Read SURVEY_MACHINE_URL and SURVEY_MACHINE_KEY from your application's environment.
Use an integration key with only the permissions needed. The examples list surveys;
keep response data out of logs in a real integration.

Python, standard library:

~~~python
import json, os
from urllib.request import Request, urlopen

request = Request(
    os.environ["SURVEY_MACHINE_URL"].rstrip("/") + "/api/v1/surveys",
    headers={"X-API-Key": os.environ["SURVEY_MACHINE_KEY"]},
)
with urlopen(request, timeout=15) as response:
    surveys = json.load(response)
~~~

Java 11+:

~~~java
var request = java.net.http.HttpRequest.newBuilder(
    java.net.URI.create(System.getenv("SURVEY_MACHINE_URL") + "/api/v1/surveys"))
    .timeout(java.time.Duration.ofSeconds(15))
    .header("X-API-Key", System.getenv("SURVEY_MACHINE_KEY")).GET().build();
var response = java.net.http.HttpClient.newHttpClient().send(
    request, java.net.http.HttpResponse.BodyHandlers.ofString());
if (response.statusCode() != 200) throw new IllegalStateException("Survey API failed");
String json = response.body();
~~~

PHP with cURL:

~~~php
$curl = curl_init(rtrim(getenv('SURVEY_MACHINE_URL'), '/') . '/api/v1/surveys');
curl_setopt_array($curl, [
    CURLOPT_HTTPHEADER => ['X-API-Key: ' . getenv('SURVEY_MACHINE_KEY')],
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT => 15,
]);
$json = curl_exec($curl);
if ($json === false || curl_getinfo($curl, CURLINFO_HTTP_CODE) !== 200) {
    throw new RuntimeException('Survey API request failed');
}
$surveys = json_decode($json, true, 512, JSON_THROW_ON_ERROR);
curl_close($curl);
~~~

C applications can use libcurl to issue the same requests: set CURLOPT_URL,
CURLOPT_HTTPHEADER with X-API-Key and Content-Type: application/json, a finite
timeout, and a response callback. Parse the JSON with your chosen JSON library.
There is no special C server or C-specific API branch to deploy.

## Browser sessions and administration

The app uses /auth/login, /auth/check, /auth/logout and /auth/activate.
Login/activation sets a 12-hour HttpOnly, SameSite=Lax cookie (Secure in production).
Unsafe authenticated browser requests also require X-CSRF-Token, returned by
login/check. Cookie authentication is same-origin; allowlisted CORS is for
integration keys/public calls, not browser sessions across sites.

Operators use /operator/customers, /operator/customers/{id}/reset and
PUT /operator/customers/{id} with {"enabled": false} to manage access. Invitations
and recovery links use a URL fragment to keep their one-time token out of ordinary
HTTP request URLs. Deliver them privately and do not log them.

## Errors and retries

401 means missing/invalid authentication. 403 means insufficient permission or CSRF/
origin rejection. 404 includes another account's survey. 409 means a stale revision,
changed survey or conflicting submission ID. 410 means a closed public survey.
422 describes invalid fields without echoing answers/passwords. 413 means the
512 KiB request limit was exceeded. 429 includes Retry-After for login throttling.
503 from /health means the database or schema is not ready.

Retry transient network/server failures with backoff. Retry submissions using the
same submission_id. After a 409 draft edit, fetch the latest survey and let the owner
reconcile changes rather than overwriting them.
