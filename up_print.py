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
REQUIRED_APP_ROLES = {"Printer.Read.All", "PrintJob.ReadWrite.All", "PrintJob.Manage.All"}

# Ensure uncommon but relevant types are recognized by extension
mimetypes.add_type("application/oxps", ".oxps")
mimetypes.add_type("application/vnd.ms-xpsdocument", ".xps")
mimetypes.add_type("application/pdf", ".pdf")
mimetypes.add_type("image/jpeg", ".jpg")
mimetypes.add_type("image/jpeg", ".jpeg")
mimetypes.add_type("image/png", ".png")


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


def get_user_token_device_code(tenant_id: str, client_id: str, scopes: List[str], cache_path: Optional[str] = None) -> str:
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    token_cache: Optional[msal.SerializableTokenCache] = None
    if cache_path:
        token_cache = msal.SerializableTokenCache()
        if os.path.exists(cache_path):
            try:
                token_cache.deserialize(open(cache_path, "r").read())
            except Exception:  # noqa: BLE001
                pass
    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=authority,
        token_cache=token_cache,
    )
    accounts = app.get_accounts()
    result: Optional[Dict[str, Any]] = None
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
    if not result:
        flow = app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            raise RuntimeError(f"Failed to initiate device code flow: {flow}")
        print(flow["message"])  # prompts user to visit URL and enter code
        result = app.acquire_token_by_device_flow(flow)
    if not result or "access_token" not in result:
        raise RuntimeError(f"Failed to acquire user token: {result}")
    if token_cache and cache_path:
        try:
            open(cache_path, "w").write(token_cache.serialize())
        except Exception:  # noqa: BLE001
            pass
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
        "raw_response": None,
    }
    try:
        data = resp.json()
        details["raw_response"] = data
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


def _sniff_magic_content_type(file_path: str) -> Optional[str]:
    """Best-effort magic-byte MIME sniffing for common printable formats.

    This intentionally focuses on formats commonly supported by Universal Print
    (PDF, JPEG, PNG, GIF, TIFF, PostScript, XPS/OXPS by extension disambiguation).
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
    except Exception:  # noqa: BLE001
        return None

    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\xFF\xD8\xFF"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "image/gif"
    if header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
        return "image/tiff"
    if header.startswith(b"%!PS-"):
        return "application/postscript"

    # ZIP container (docx/xlsx/pptx/oxps/xps). Disambiguate by extension only.
    if header.startswith(b"PK\x03\x04") or header.startswith(b"PK\x05\x06") or header.startswith(b"PK\x07\x08"):
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".docx":
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if ext == ".xlsx":
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if ext == ".pptx":
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if ext == ".oxps":
            return "application/oxps"
        if ext == ".xps":
            return "application/vnd.ms-xpsdocument"
        # Unknown ZIP-based format; let caller handle fallback
        return None

    return None


def detect_content_type(file_path: str, explicit_content_type: Optional[str], debug: bool = False) -> Tuple[str, str]:
    """Determine the best contentType for a document.

    Order of precedence:
    1) Explicit override from CLI/env
    2) Extension-based guess via mimetypes
    3) Magic-byte sniffing for common formats
    4) Fallback to application/octet-stream

    Returns a tuple of (content_type, source) where source describes how it was determined.
    """
    if explicit_content_type:
        return explicit_content_type, "override"

    guessed_type, _ = mimetypes.guess_type(file_path)
    if guessed_type and guessed_type != "application/octet-stream":
        return guessed_type, "extension"

    sniffed = _sniff_magic_content_type(file_path)
    if sniffed:
        return sniffed, "magic"

    return "application/octet-stream", "fallback"


def _noop() -> None:
    return None


def _discover_printer_shares(token: str, printer_id: str, debug: bool = False, retry_count: int = 2) -> List[Dict[str, Any]]:
    """Discover all shares for a given printer.
    
    Returns a list of share objects that reference this printer.
    Returns empty list if no shares found or on error.
    Includes retry logic for transient failures.
    """
    for attempt in range(retry_count + 1):
        try:
            # Try using $expand to get printer info directly
            shares_url = f"{GRAPH_BASE_URL}/print/shares?$expand=printer"
            if debug and attempt > 0:
                print(f"[debug] shares discovery attempt {attempt + 1}/{retry_count + 1}", file=sys.stderr)
            
            shares_resp = requests.get(shares_url, headers=graph_headers(token), timeout=30)
            
            if shares_resp.status_code != 200:
                if debug:
                    print(f"[debug] shares discovery failed: {_build_graph_error_message('List shares', shares_resp)}", file=sys.stderr)
                if attempt < retry_count:
                    time.sleep(2)  # Wait before retry
                    continue
                return []
            
            shares_data = shares_resp.json() or {}
            shares = shares_data.get("value") or []
            
            if debug:
                print(f"[debug] total shares found: {len(shares)}", file=sys.stderr)
            
            # Filter shares to find ones matching this printer
            matching_shares = []
            for s in shares:
                printer_ref = s.get("printer") or {}
                share_printer_id = printer_ref.get("id")
                if share_printer_id == printer_id:
                    matching_shares.append(s)
                    if debug:
                        share_id = s.get("id")
                        share_name = s.get("displayName") or "unnamed"
                        print(f"[debug] found matching share: {share_id} ({share_name})", file=sys.stderr)
            
            if matching_shares or attempt >= retry_count:
                return matching_shares
            
            # No matches found, wait and retry
            if debug:
                print(f"[debug] no matching shares found, retrying...", file=sys.stderr)
            time.sleep(2)
            
        except Exception as e:  # noqa: BLE001
            if debug:
                print(f"[debug] exception discovering shares: {e}", file=sys.stderr)
            if attempt < retry_count:
                time.sleep(2)
                continue
            return []
    
    return []


def create_print_job(token: str, printer_id: str, job_name: str, job_configuration: Optional[Dict[str, Any]] = None, debug: bool = False, share_id: Optional[str] = None) -> Tuple[Dict, Optional[str]]:
    """Create a print job, optionally via a share endpoint.
    
    Returns tuple of (job_dict, share_id_used).
    If share_id is provided, creates via /print/shares/{shareId}/jobs.
    Otherwise creates via /print/printers/{printerId}/jobs.
    """
    if share_id:
        url = f"{GRAPH_BASE_URL}/print/shares/{share_id}/jobs"
        if debug:
            print(f"[debug] creating job via share: {share_id}", file=sys.stderr)
    else:
        url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs"
        if debug:
            print(f"[debug] creating job via printer: {printer_id}", file=sys.stderr)
    
    payload: Dict[str, Any] = {"displayName": job_name}
    if job_configuration:
        payload["configuration"] = job_configuration
    
    resp = requests.post(url, headers=graph_headers(token), json=payload, timeout=60)
    if resp.status_code not in (200, 201):
        raise RuntimeError(_build_graph_error_message("Create job", resp))
    
    return resp.json(), share_id


def create_document_and_upload_session(
    token: str,
    printer_id: str,
    job_id: str,
    file_path: str,
    content_type: Optional[str],
    debug: bool = False,
    share_id: Optional[str] = None,
) -> Tuple[str, str]:
    file_name = os.path.basename(file_path)
    effective_content_type, ctype_source = detect_content_type(file_path, content_type, debug=debug)
    if debug:
        try:
            print(f"[debug] resolved contentType: {effective_content_type} (source={ctype_source})", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass

    # Optional: verify the job exists (helps diagnose bad IDs or scope mismatches)
    if debug:
        try:
            printer_job_url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}?$select=id,createdDateTime,status"
            printer_job_resp = requests.get(printer_job_url, headers=graph_headers(token), timeout=30)
            if printer_job_resp.status_code == 200:
                job_meta = printer_job_resp.json() or {}
                print(f"[debug] job ok: {job_meta.get('id')}", file=sys.stderr)
                job_status = job_meta.get("status") or {}
                if job_status:
                    print(f"[debug] job status: {json.dumps(job_status, separators=(',', ':'), ensure_ascii=False)}", file=sys.stderr)
            else:
                print(f"[debug] printer job lookup: {_build_graph_error_message('Get printer job', printer_job_resp)}", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
        
        # Also try to access via the shares endpoint as alternative
        try:
            matching_shares = _discover_printer_shares(token, printer_id, debug=debug)
            if matching_shares:
                share_id = matching_shares[0].get("id")
                print(f"[debug] discovered printer share: {share_id}", file=sys.stderr)
                # Try to access job via share endpoint
                share_job_url = f"{GRAPH_BASE_URL}/print/shares/{share_id}/jobs/{job_id}?$select=id,createdDateTime,status"
                share_job_resp = requests.get(share_job_url, headers=graph_headers(token), timeout=30)
                if share_job_resp.status_code == 200:
                    print(f"[debug] job accessible via share endpoint", file=sys.stderr)
                else:
                    print(f"[debug] share job lookup failed: {_build_graph_error_message('Get share job', share_job_resp)}", file=sys.stderr)
            else:
                print(f"[debug] no shares found for printer", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass

    # Strategy 1: Try the modern createUploadSession on documents collection
    # Use share endpoint if available, otherwise use printer endpoint
    if share_id:
        collection_session_url = f"{GRAPH_BASE_URL}/print/shares/{share_id}/jobs/{job_id}/documents/createUploadSession"
    else:
        collection_session_url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}/documents/createUploadSession"
    
    collection_payload = {
        "documentName": file_name,
        "contentType": effective_content_type,
        "size": os.path.getsize(file_path),
    }
    try:
        if debug:
            try:
                endpoint_type = "share" if share_id else "printer"
                print(f"[debug] Strategy 1 (via {endpoint_type}): POST {collection_session_url}", file=sys.stderr)
                print(f"[debug] body={json.dumps(collection_payload, separators=(',', ':'), ensure_ascii=False)}", file=sys.stderr)
            except Exception:  # noqa: BLE001
                pass
        session_resp = requests.post(collection_session_url, headers=graph_headers(token), json=collection_payload, timeout=60)
        if session_resp.status_code in (200, 201):
            upload_session = session_resp.json() or {}
            # Try multiple shapes for document id for robustness across API surfaces
            document_id = (
                upload_session.get("documentId")
                or (upload_session.get("document") or {}).get("id")
                or upload_session.get("id")
            )
            upload_url = upload_session.get("uploadUrl")
            if upload_url:
                if debug:
                    print(f"[debug] Strategy 1 succeeded", file=sys.stderr)
                return document_id or "", upload_url
        # Strategy failed
        if debug:
            try:
                err_details = _extract_graph_error(session_resp)
                print(f"[debug] Strategy 1 failed: {_build_graph_error_message('Create upload session (collection)', session_resp)}", file=sys.stderr)
                if err_details.get("raw_response"):
                    print(f"[debug] response body: {json.dumps(err_details['raw_response'], separators=(',', ':'), ensure_ascii=False)}", file=sys.stderr)
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        if debug:
            print(f"[debug] Strategy 1 exception: {e}", file=sys.stderr)

    # Strategy 2: Legacy two-step flow - create document first
    # Use share endpoint if available, otherwise use printer endpoint
    if share_id:
        doc_url = f"{GRAPH_BASE_URL}/print/shares/{share_id}/jobs/{job_id}/documents"
    else:
        doc_url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}/documents"
    
    doc_payload = {"displayName": file_name, "contentType": effective_content_type}
    if debug:
        try:
            endpoint_type = "share" if share_id else "printer"
            print(f"[debug] Strategy 2 (via {endpoint_type}): POST {doc_url}", file=sys.stderr)
            print(f"[debug] body={json.dumps(doc_payload, separators=(',', ':'), ensure_ascii=False)}", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
    
    doc_resp = requests.post(doc_url, headers=graph_headers(token), json=doc_payload, timeout=60)
    
    # Strategy 2 failed, try Strategy 3: Use shares endpoint if we haven't already
    if doc_resp.status_code not in (200, 201):
        if debug:
            try:
                err_details = _extract_graph_error(doc_resp)
                print(f"[debug] Strategy 2 failed: {_build_graph_error_message('Create document', doc_resp)}", file=sys.stderr)
                if err_details.get("raw_response"):
                    print(f"[debug] response body: {json.dumps(err_details['raw_response'], separators=(',', ':'), ensure_ascii=False)}", file=sys.stderr)
            except Exception:  # noqa: BLE001
                pass
        
        # Strategy 3: Try to use printer share endpoint (only if we weren't already using it)
        if not share_id:
            try:
                if debug:
                    print(f"[debug] Strategy 3: Attempting via printer share endpoint", file=sys.stderr)
                
                # Discover the share ID for this printer
                matching_shares = _discover_printer_shares(token, printer_id, debug=debug)
                
                if matching_shares:
                    discovered_share_id = matching_shares[0].get("id")
                    if debug:
                        print(f"[debug] using share ID: {discovered_share_id}", file=sys.stderr)
                    
                    # Try to create document via share endpoint
                    share_doc_url = f"{GRAPH_BASE_URL}/print/shares/{discovered_share_id}/jobs/{job_id}/documents"
                    if debug:
                        print(f"[debug] POST {share_doc_url}", file=sys.stderr)
                    
                    share_doc_resp = requests.post(share_doc_url, headers=graph_headers(token), json=doc_payload, timeout=60)
                    
                    if share_doc_resp.status_code in (200, 201):
                        if debug:
                            print(f"[debug] Strategy 3 succeeded!", file=sys.stderr)
                        doc_resp = share_doc_resp  # Use this response
                        share_id = discovered_share_id  # Update for session URL
                    else:
                        if debug:
                            print(f"[debug] Strategy 3 failed: {_build_graph_error_message('Create document (share)', share_doc_resp)}", file=sys.stderr)
                else:
                    if debug:
                        print(f"[debug] Strategy 3 skipped: no shares found", file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                if debug:
                    print(f"[debug] Strategy 3 exception: {e}", file=sys.stderr)
        else:
            if debug:
                print(f"[debug] Strategy 3 skipped: already using share endpoint", file=sys.stderr)
    
    # Check if any strategy for document creation worked
    if doc_resp.status_code not in (200, 201):
        err_msg = _build_graph_error_message("Create document", doc_resp)
        
        # Extract error details for better diagnostics
        err_details = _extract_graph_error(doc_resp)
        error_code = err_details.get("error_code")
        
        # Provide more specific guidance based on the error
        if error_code == "UnknownError" and doc_resp.status_code == 404:
            guidance = (
                "\n\nThe job was created but documents cannot be attached (404 UnknownError).\n"
                "All fallback strategies (printer endpoint, share endpoint) have been exhausted.\n"
                "This typically indicates one of the following:\n\n"
                "1. The printer is not properly shared or the share is not accessible\n"
                "   → In Azure Portal, go to Universal Print and verify the printer has at least one active share\n"
                "   → Check that PrinterShare.ReadWrite.All permission is granted and admin consent is completed\n"
                "   → Wait a few minutes after creating a share for it to become active\n\n"
                "2. The Universal Print connector may be offline or misconfigured\n"
                "   → Verify the connector is online in the Universal Print portal\n"
                "   → Check the connector event logs on the Windows machine running the connector\n\n"
                "3. The printer may not support document attachments immediately after job creation\n"
                "   → This is a known timing issue with some printer/connector configurations\n"
                "   → Try waiting 30-60 seconds before attempting to print\n\n"
                "4. API permissions may be insufficient\n"
                "   → Ensure your app has: Printer.Read.All, PrintJob.ReadWrite.All, PrintJob.Manage.All, PrinterShare.ReadWrite.All\n"
                "   → Verify admin consent has been granted for all permissions\n\n"
                "Run with --debug for detailed diagnostics showing which strategies were attempted."
            )
        else:
            guidance = (
                "\n\nAll strategies failed. This may indicate:\n"
                "1. Missing PrinterShare.ReadWrite.All permission\n"
                "2. Job was created but is not accessible for document upload\n"
                "3. Printer or connector configuration issue\n"
                "4. API version incompatibility\n\n"
                "Try running with --debug for detailed diagnostics."
            )
        
        raise RuntimeError(f"{err_msg}{guidance}")
    
    document = doc_resp.json() or {}
    document_id = document.get("id")
    if not document_id:
        raise RuntimeError("Document ID missing in create document response")
    
    if debug:
        print(f"[debug] document created: {document_id}", file=sys.stderr)

    # Now create upload session for the document
    # Use share endpoint if available, otherwise use printer endpoint
    if share_id:
        session_url = f"{GRAPH_BASE_URL}/print/shares/{share_id}/jobs/{job_id}/documents/{document_id}/createUploadSession"
    else:
        session_url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}/documents/{document_id}/createUploadSession"
    
    if debug:
        try:
            endpoint_type = "share" if share_id else "printer"
            print(f"[debug] Creating upload session (via {endpoint_type}): POST {session_url} body={{}}", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
    session_resp = requests.post(session_url, headers=graph_headers(token), json={}, timeout=60)
    if session_resp.status_code not in (200, 201):
        raise RuntimeError(_build_graph_error_message("Create upload session", session_resp))
    upload_session = session_resp.json() or {}
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


def start_print_job(token: str, printer_id: str, job_id: str, share_id: Optional[str] = None, debug: bool = False) -> None:
    """Start a print job, optionally via a share endpoint."""
    if share_id:
        url = f"{GRAPH_BASE_URL}/print/shares/{share_id}/jobs/{job_id}/start"
        if debug:
            print(f"[debug] starting job via share: {share_id}", file=sys.stderr)
    else:
        url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}/start"
        if debug:
            print(f"[debug] starting job via printer: {printer_id}", file=sys.stderr)
    
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


def _get_printer_defaults(token: str, printer_id: str, debug: bool = False) -> Dict[str, Any]:
    """Fetch printer defaults for use in job configuration.

    Tries to read `defaults` from the printer resource. Returns an empty dict
    on failure so callers can decide how to proceed.
    """
    url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}?$select=defaults"
    resp = requests.get(url, headers=graph_headers(token), timeout=30)
    if resp.status_code != 200:
        if debug:
            print(f"[debug] could not fetch printer defaults: {_build_graph_error_message('Get printer defaults', resp)}", file=sys.stderr)
        return {}
    data = resp.json() or {}
    defaults = data.get("defaults") or {}
    if debug:
        try:
            print(f"[debug] printer defaults: {json.dumps(defaults, separators=(',', ':'), ensure_ascii=False)}", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
    return defaults


def _get_printer_capabilities(token: str, printer_id: str, debug: bool = False) -> Dict[str, Any]:
    """Fetch printer capabilities to check supported content types.

    Returns an empty dict on failure so callers can decide how to proceed.
    """
    url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}?$select=capabilities"
    resp = requests.get(url, headers=graph_headers(token), timeout=30)
    if resp.status_code != 200:
        if debug:
            print(f"[debug] could not fetch printer capabilities: {_build_graph_error_message('Get printer capabilities', resp)}", file=sys.stderr)
        return {}
    data = resp.json() or {}
    capabilities = data.get("capabilities") or {}
    if debug:
        try:
            content_types = capabilities.get("contentTypes") or []
            if content_types:
                print(f"[debug] printer supported content types: {json.dumps(content_types, separators=(',', ':'), ensure_ascii=False)}", file=sys.stderr)
            else:
                print(f"[debug] printer capabilities: {json.dumps(capabilities, separators=(',', ':'), ensure_ascii=False)}", file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
    return capabilities


def _build_job_configuration_from_defaults(defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Translate printer defaults to a print job configuration.

    Only includes properties present in defaults and recognized by the API.
    """
    if not isinstance(defaults, dict):
        return {}
    allowed_keys = {
        "copies",
        "colorMode",
        "duplexMode",
        "quality",
        "dpi",
        "orientation",
        "mediaSize",
        "mediaType",
        "pagesPerSheet",
        "margins",
        "finishings",
        "fitPdfToPage",
    }
    configuration: Dict[str, Any] = {}
    for key in allowed_keys:
        value = defaults.get(key)
        if value is not None:
            configuration[key] = value
    # Ensure at least copies is set; some connectors require it
    if "copies" not in configuration:
        configuration["copies"] = 1
    return configuration


def main() -> int:
    load_env()

    parser = argparse.ArgumentParser(description="Create and start a Universal Print job via Microsoft Graph")
    parser.add_argument("--printer-id", default=os.getenv("PRINTER_ID"), help="Printer ID in Universal Print")
    # Share functionality removed; use printer-id endpoints only
    parser.add_argument("--file", dest="file_path", default=os.getenv("FILE_PATH"), help="Path to file to print (PDF, XPS, etc.)")
    parser.add_argument("--job-name", default="UP Job", help="Display name for the print job")
    parser.add_argument("--poll", action="store_true", help="Poll job status until completion")
    parser.add_argument("--content-type", dest="content_type", default=None, help="Override document contentType (e.g., application/pdf)")
    parser.add_argument("--debug", action="store_true", help="Print token claims and verbose diagnostics")
    parser.add_argument("--auth", choices=["app", "device"], default=os.getenv("AUTH", "app"), help="Authentication mode: app (client credentials) or device (device code delegated)")
    parser.add_argument("--scopes", nargs="*", default=os.getenv("SCOPES", "Printer.Read.All PrintJob.ReadWrite.All PrintJob.Manage.All offline_access").split(), help="Delegated scopes for device auth (space-separated)")
    parser.add_argument("--cache-path", default=os.getenv("MSAL_CACHE_PATH", os.path.expanduser("~/.msal_up_cli_cache.json")), help="Path to MSAL token cache for device auth")
    parser.add_argument("--tenant-id", default=os.getenv("TENANT_ID"), help="Azure AD tenant ID")
    parser.add_argument("--client-id", default=os.getenv("CLIENT_ID"), help="App registration client ID")
    parser.add_argument("--client-secret", default=os.getenv("CLIENT_SECRET"), help="App registration client secret")
    args = parser.parse_args()

    required_base = [
        ("--tenant-id", args.tenant_id),
        ("--client-id", args.client_id),
        ("--printer-id", args.printer_id),
        ("--file", args.file_path),
    ]
    if args.auth == "app":
        required_base.append(("--client-secret", args.client_secret))
    missing = [name for name, val in required_base if not val]
    if missing:
        print(f"Missing required arguments: {' '.join(missing)}", file=sys.stderr)
        return 2
    if not os.path.exists(args.file_path):
        print(f"File not found: {args.file_path}", file=sys.stderr)
        return 2

    try:
        if args.auth == "app":
            token = get_access_token(args.tenant_id, args.client_id, args.client_secret)
        else:
            token = get_user_token_device_code(args.tenant_id, args.client_id, args.scopes, cache_path=args.cache_path)
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

        # Check printer capabilities and supported content types
        if args.debug:
            capabilities = _get_printer_capabilities(token, args.printer_id, debug=args.debug)
            content_types = capabilities.get("contentTypes") or []
            if content_types:
                content_type_to_check, _ = detect_content_type(args.file_path, args.content_type, debug=False)
                if content_type_to_check not in content_types:
                    print(f"[debug] WARNING: Content type '{content_type_to_check}' may not be supported by printer", file=sys.stderr)
                    print(f"[debug] Supported types: {json.dumps(content_types, separators=(',', ':'), ensure_ascii=False)}", file=sys.stderr)

        # Build job configuration from printer defaults to avoid 400 Missing configuration
        defaults = _get_printer_defaults(token, args.printer_id, debug=args.debug)
        job_configuration = _build_job_configuration_from_defaults(defaults)
        if args.debug and job_configuration:
            try:
                print(f"[debug] job configuration: {json.dumps(job_configuration, separators=(',', ':'), ensure_ascii=False)}", file=sys.stderr)
            except Exception:  # noqa: BLE001
                pass

        # Discover printer shares before creating the job
        # This allows us to create the job via the share endpoint which is often more reliable
        matching_shares = _discover_printer_shares(token, args.printer_id, debug=args.debug)
        preferred_share_id = None
        if matching_shares:
            preferred_share_id = matching_shares[0].get("id")
            if args.debug:
                print(f"[debug] will use share endpoint for job creation: {preferred_share_id}", file=sys.stderr)
        elif args.debug:
            print(f"[debug] no shares found, will use printer endpoint for job creation", file=sys.stderr)

        job, job_share_id = create_print_job(
            token, 
            args.printer_id, 
            args.job_name, 
            job_configuration=job_configuration or None, 
            debug=args.debug,
            share_id=preferred_share_id
        )
        job_id = job.get("id")
        if not job_id:
            raise RuntimeError("Job ID missing in create job response")
        print(f"Created job {job_id}")

        _, upload_url = create_document_and_upload_session(
            token,
            args.printer_id,
            job_id,
            args.file_path,
            args.content_type,
            debug=args.debug,
            share_id=job_share_id,
        )
        print("Uploading document...")
        upload_file_to_upload_session(upload_url, args.file_path)
        print("Upload complete.")

        print("Starting job...")
        start_print_job(token, args.printer_id, job_id, share_id=job_share_id, debug=args.debug)
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

