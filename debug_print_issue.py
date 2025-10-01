#!/usr/bin/env python3
"""
Debug script to help diagnose Universal Print 404 errors
"""
import os
import sys
import json
import requests
from dotenv import load_dotenv
from up_print import get_access_token, graph_headers, _build_graph_error_message, GRAPH_BASE_URL

def debug_printer_and_job(token, printer_id, job_id):
    """Debug printer and job accessibility"""
    print("=== DEBUGGING PRINTER AND JOB ACCESS ===")
    
    # 1. Check printer access
    print(f"\n1. Checking printer access: {printer_id}")
    printer_url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}?$select=id,displayName,manufacturer,model,capabilities,defaults"
    resp = requests.get(printer_url, headers=graph_headers(token), timeout=30)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        printer_data = resp.json()
        print(f"   Printer: {printer_data.get('displayName')} ({printer_data.get('manufacturer')} {printer_data.get('model')})")
        
        # Check capabilities for supported formats
        capabilities = printer_data.get('capabilities', {})
        supported_formats = capabilities.get('supportedDocumentMimeTypes', [])
        print(f"   Supported formats: {supported_formats}")
        
        # Check defaults
        defaults = printer_data.get('defaults', {})
        print(f"   Default content type: {defaults.get('contentType', 'Not specified')}")
    else:
        print(f"   Error: {_build_graph_error_message('Get printer', resp)}")
        return False
    
    # 2. Check job access
    print(f"\n2. Checking job access: {job_id}")
    job_url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}?$select=id,createdDateTime,status"
    resp = requests.get(job_url, headers=graph_headers(token), timeout=30)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        job_data = resp.json()
        print(f"   Job: {job_data.get('id')} created at {job_data.get('createdDateTime')}")
        status = job_data.get('status', {})
        print(f"   Status: {status.get('state', 'unknown')} - {status.get('description', 'no description')}")
    else:
        print(f"   Error: {_build_graph_error_message('Get job', resp)}")
        return False
    
    # 3. Check documents collection access
    print(f"\n3. Checking documents collection access")
    docs_url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}/documents"
    resp = requests.get(docs_url, headers=graph_headers(token), timeout=30)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        docs_data = resp.json()
        documents = docs_data.get('value', [])
        print(f"   Documents count: {len(documents)}")
        for doc in documents:
            print(f"     - {doc.get('id')}: {doc.get('displayName')} ({doc.get('contentType')})")
    else:
        print(f"   Error: {_build_graph_error_message('Get documents', resp)}")
    
    return True

def test_upload_session_creation(token, printer_id, job_id, file_path):
    """Test upload session creation with different approaches"""
    print("\n=== TESTING UPLOAD SESSION CREATION ===")
    
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    
    # Test 1: Collection upload session (preferred method)
    print(f"\n1. Testing collection upload session")
    collection_url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}/documents/createUploadSession"
    payload = {
        "documentName": file_name,
        "contentType": "application/pdf",
        "size": file_size
    }
    print(f"   URL: {collection_url}")
    print(f"   Payload: {json.dumps(payload, indent=2)}")
    
    resp = requests.post(collection_url, headers=graph_headers(token), json=payload, timeout=60)
    print(f"   Status: {resp.status_code}")
    if resp.status_code in (200, 201):
        print("   SUCCESS: Collection upload session created")
        return True
    else:
        print(f"   FAILED: {_build_graph_error_message('Collection upload session', resp)}")
    
    # Test 2: Try with different content types
    print(f"\n2. Testing with different content types")
    content_types = ["application/oxps", "application/vnd.ms-xpsdocument", "application/octet-stream"]
    
    for content_type in content_types:
        print(f"\n   Testing with content type: {content_type}")
        payload["contentType"] = content_type
        resp = requests.post(collection_url, headers=graph_headers(token), json=payload, timeout=60)
        print(f"   Status: {resp.status_code}")
        if resp.status_code in (200, 201):
            print(f"   SUCCESS: Upload session created with {content_type}")
            return True
        else:
            print(f"   FAILED: {_build_graph_error_message(f'Upload session with {content_type}', resp)}")
    
    # Test 3: Fallback method - create document first
    print(f"\n3. Testing fallback method (create document first)")
    doc_url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}/documents"
    doc_payload = {
        "displayName": file_name,
        "contentType": "application/pdf"
    }
    print(f"   URL: {doc_url}")
    print(f"   Payload: {json.dumps(doc_payload, indent=2)}")
    
    resp = requests.post(doc_url, headers=graph_headers(token), json=doc_payload, timeout=60)
    print(f"   Status: {resp.status_code}")
    if resp.status_code in (200, 201):
        doc_data = resp.json()
        document_id = doc_data.get("id")
        print(f"   SUCCESS: Document created with ID {document_id}")
        
        # Now try to create upload session for this document
        session_url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs/{job_id}/documents/{document_id}/createUploadSession"
        print(f"   Creating upload session: {session_url}")
        resp = requests.post(session_url, headers=graph_headers(token), json={}, timeout=60)
        print(f"   Status: {resp.status_code}")
        if resp.status_code in (200, 201):
            print("   SUCCESS: Upload session created for document")
            return True
        else:
            print(f"   FAILED: {_build_graph_error_message('Document upload session', resp)}")
    else:
        print(f"   FAILED: {_build_graph_error_message('Create document', resp)}")
    
    return False

def main():
    load_dotenv()
    
    # Get required parameters
    tenant_id = os.getenv("TENANT_ID")
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    printer_id = os.getenv("PRINTER_ID")
    file_path = os.getenv("FILE_PATH")
    
    if not all([tenant_id, client_id, client_secret, printer_id, file_path]):
        print("Missing required environment variables. Please set:")
        print("- TENANT_ID")
        print("- CLIENT_ID") 
        print("- CLIENT_SECRET")
        print("- PRINTER_ID")
        print("- FILE_PATH")
        return 1
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return 1
    
    try:
        # Get access token
        print("Getting access token...")
        token = get_access_token(tenant_id, client_id, client_secret)
        print("Token acquired successfully")
        
        # Create a test job
        print("\nCreating test job...")
        job_url = f"{GRAPH_BASE_URL}/print/printers/{printer_id}/jobs"
        job_payload = {"displayName": "Debug Test Job"}
        resp = requests.post(job_url, headers=graph_headers(token), json=job_payload, timeout=60)
        
        if resp.status_code not in (200, 201):
            print(f"Failed to create job: {_build_graph_error_message('Create job', resp)}")
            return 1
        
        job_data = resp.json()
        job_id = job_data.get("id")
        print(f"Created test job: {job_id}")
        
        # Run diagnostics
        if debug_printer_and_job(token, printer_id, job_id):
            test_upload_session_creation(token, printer_id, job_id, file_path)
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())