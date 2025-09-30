#!/usr/bin/env python3
import argparse
import os
import sys
import time
import mimetypes
import json
import base64
from typing import Dict, Optional, Tuple, Any, List

import msal
import requests
from dotenv import load_dotenv


GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
REQUIRED_APP_ROLES = {"Printer.Read.All", "PrintJob.ReadWrite.All"}


def load_env() -> None:
    # Load .env if present; environment variables take precedence
    load_dotenv(override=False)


def get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )
    result = app.acquire_token_for_client(scopes=GRAPH_SCOPE)
    if "access_token" not in result:
        raise RuntimeError(f"Failed to acquire token: {result}")
    return result["access_token"]


def _base64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def decode_jwt_without_validation(token: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b = _base64url_decode(parts[1])
        return json.loads(payload_b.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def debug_print_token_claims(token: str) -> None:
    claims = decode_jwt_without_validation(token)
    if not claims:
        print("[debug] Unable to decode access token claims", file=sys.stderr)
        return
    tenant_id = claims.get("tid")
    audience = claims.get("aud")
    app_id = claims.get("appid") or claims.get("azp")
    roles: List[str] = claims.get("roles") or []
    scopes = claims.get("scp")
    print(f"[debug] token.aud={audience} tid={tenant_id} appid={app_id}", file=sys.stderr)
    if roles:
        print(f"[debug] token.roles={roles}", file=sys.stderr)
        missing = sorted(REQUIRED_APP_ROLES.difference(set(roles)))
        if missing:
            print(f"[debug] missing app roles: {missing}", file=sys.stderr)
    if scopes:
        print(f"[debug] token.scp={scopes}", file=sys.stderr)


def _extract_graph_error(resp: requests.Response) -> Dict[str, Any]:
    details: Dict[str, Any] = {
        "status_code": resp.status_code,
        "text": resp.text,
        "request_id": resp.headers.get("request-id") or resp.headers.get("x-ms-request-id"),
        "client_request_id": resp.headers.get("client-request-id"),
        "error_code": None,
        "message": None,
        "inner_request_id": None,
        "inner_client_request_id": None,
    }
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        data = None
    if isinstance(data, dict) and data.get("error"):
        err = data.get("error")
        if isinstance(err, dict):
            details["error_code"] = err.get("code")
            msg = err.get("message")
            if isinstance(msg, str):
                details["message"] = msg
            inner = err.get("innerError") or {}
            if isinstance(inner, dict):
                details["inner_request_id"] = inner.get("request-id") or inner.get("requestId")
                details["inner_client_request_id"] = inner.get("client-request-id") or inner.get("clientRequestId")
    return details


def _build_graph_error_message(action: str, resp: requests.Response) -> str:
    d = _extract_graph_error(resp)
    id_hint = d.get("request_id") or d.get("inner_request_id")
    client_id_hint = d.get("client_request_id") or d.get("inner_client_request_id")
    parts = [
        f"{action} failed: {d['status_code']}",
    ]
    if d.get("error_code"):
        parts.append(f"code={d['error_code']}")
    if d.get("message"):
        parts.append(f"message={d['message']}")
    if id_hint:
        parts.append(f"request-id={id_hint}")
    if client_id_hint:
        parts.append(f"client-request-id={client_id_hint}")
    return " ".join(parts)


def graph_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def create_print_job(token: str, printer_id: str, job_name: str) -> Dict:
    url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs"
    payload = {"displayName": job_name}
    resp = requests.post(url, headers=graph_headers(token), json=payload, timeout=60)
    if resp.status_code not in (200, 201):
        raise RuntimeError(_build_graph_error_message("Create job", resp))
    return resp.json()


def create_document_and_upload_session(token: str, printer_id: str, job_id: str, file_path: str, content_type: Optional[str]) -> Tuple[str, str]:
    file_name = os.path.basename(file_path)
    guessed_type, _ = mimetypes.guess_type(file_path)
    effective_content_type = content_type or guessed_type or "application/octet-stream"

    # 1) Create document on the job
    doc_url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}/documents"
    doc_payload = {"displayName": file_name, "contentType": effective_content_type}
    doc_resp = requests.post(doc_url, headers=graph_headers(token), json=doc_payload, timeout=60)
    if doc_resp.status_code not in (200, 201):
        raise RuntimeError(_build_graph_error_message("Create document", doc_resp))
    document = doc_resp.json()
    document_id = document.get("id")
    if not document_id:
        raise RuntimeError("Document ID missing in create document response")

    # 2) Create upload session
    session_url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}/documents/{document_id}/createUploadSession"
    session_resp = requests.post(session_url, headers=graph_headers(token), json={}, timeout=60)
    if session_resp.status_code not in (200, 201):
        raise RuntimeError(_build_graph_error_message("Create upload session", session_resp))
    upload_session = session_resp.json()
    upload_url = upload_session.get("uploadUrl")
    if not upload_url:
        raise RuntimeError("uploadUrl missing in upload session response")

    return document_id, upload_url


def upload_file_to_upload_session(upload_url: str, file_path: str, chunk_size: int = 4 * 1024 * 1024) -> None:
    total_size = os.path.getsize(file_path)
    bytes_uploaded = 0
    with open(file_path, "rb") as f:
        while bytes_uploaded < total_size:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            start = bytes_uploaded
            end = bytes_uploaded + len(chunk) - 1
            headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{total_size}",
                "Content-Type": "application/octet-stream",
            }
            put_resp = requests.put(upload_url, headers=headers, data=chunk, timeout=300)
            if put_resp.status_code not in (200, 201, 202):
                raise RuntimeError(
                    f"Upload chunk failed: {put_resp.status_code} {put_resp.text} at range {start}-{end}"
                )
            bytes_uploaded = end + 1


def start_print_job(token: str, printer_id: str, job_id: str) -> None:
    url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}/start"
    resp = requests.post(url, headers=graph_headers(token), json={}, timeout=60)
    if resp.status_code not in (200, 202, 204):
        raise RuntimeError(_build_graph_error_message("Start job", resp))


def get_job(token: str, printer_id: str, job_id: str) -> Dict:
    url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}"
    resp = requests.get(url, headers=graph_headers(token), timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(_build_graph_error_message("Get job", resp))
    return resp.json()


def extract_job_state(job: Dict) -> Tuple[str, Optional[str]]:
    status = job.get("status") or {}
    state = status.get("state") or "unknown"
    description = status.get("description")
    return (state, description)


def poll_until_completed(token: str, printer_id: str, job_id: str, interval_seconds: int = 5, timeout_seconds: int = 600) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        job = get_job(token, printer_id, job_id)
        state, description = extract_job_state(job)
        print(f"Job {job_id} state: {state}{' - ' + description if description else ''}")
        if state in {"completed", "aborted", "canceled", "failed"}:
            return
        time.sleep(interval_seconds)
    raise TimeoutError("Timed out waiting for job to complete")


def main() -> int:
    load_env()

    parser = argparse.ArgumentParser(description="Create and start a Universal Print job via Microsoft Graph")
    parser.add_argument("--printer-id", default=os.getenv("PRINTER_ID"), help="Printer ID in Universal Print")
    parser.add_argument("--file", dest="file_path", default=os.getenv("FILE_PATH"), help="Path to file to print (PDF, XPS, etc.)")
    parser.add_argument("--job-name", default="UP Job", help="Display name for the print job")
    parser.add_argument("--poll", action="store_true", help="Poll job status until completion")
    parser.add_argument("--content-type", dest="content_type", default=None, help="Override document contentType (e.g., application/pdf)")
    parser.add_argument("--debug", action="store_true", help="Print token claims and verbose diagnostics")
    parser.add_argument("--tenant-id", default=os.getenv("TENANT_ID"), help="Azure AD tenant ID")
    parser.add_argument("--client-id", default=os.getenv("CLIENT_ID"), help="App registration client ID")
    parser.add_argument("--client-secret", default=os.getenv("CLIENT_SECRET"), help="App registration client secret")
    args = parser.parse_args()

    missing = [name for name, val in [
        ("--tenant-id", args.tenant_id),
        ("--client-id", args.client_id),
        ("--client-secret", args.client_secret),
        ("--printer-id", args.printer_id),
        ("--file", args.file_path),
    ] if not val]
    if missing:
        print(f"Missing required arguments: {' '.join(missing)}", file=sys.stderr)
        return 2
    if not os.path.exists(args.file_path):
        print(f"File not found: {args.file_path}", file=sys.stderr)
        return 2

    try:
        token = get_access_token(args.tenant_id, args.client_id, args.client_secret)
        if args.debug:
            debug_print_token_claims(token)

        # Preflight permission and existence check for the printer
        preflight = requests.get(
            f"{GRAPH_BASE_URL}/print/printers/{args.printer_id}?$select=id,displayName,manufacturer,model",
            headers=graph_headers(token),
            timeout=30,
        )
        if preflight.status_code == 404:
            raise RuntimeError(_build_graph_error_message("Validate printer (not found)", preflight))
        if preflight.status_code == 403:
            raise RuntimeError(_build_graph_error_message("Validate printer (forbidden)", preflight))
        if preflight.status_code != 200:
            raise RuntimeError(_build_graph_error_message("Validate printer", preflight))
        if args.debug:
            meta = preflight.json()
            print(f"[debug] printer ok: {meta.get('id')} {meta.get('displayName')}", file=sys.stderr)

        job = create_print_job(token, args.printer_id, args.job_name)
        job_id = job.get("id")
        if not job_id:
            raise RuntimeError("Job ID missing in create job response")
        print(f"Created job {job_id}")

        _, upload_url = create_document_and_upload_session(token, args.printer_id, job_id, args.file_path, args.content_type)
        print("Uploading document...")
        upload_file_to_upload_session(upload_url, args.file_path)
        print("Upload complete.")

        print("Starting job...")
        start_print_job(token, args.printer_id, job_id)
        print("Job started.")

        if args.poll:
            poll_until_completed(token, args.printer_id, job_id)
            print("Job finished.")

        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

