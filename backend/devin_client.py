import httpx
import os
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DevinClient:
    def __init__(self):
        self.api_key = os.getenv("DEVIN_API_KEY")
        self.org_id = os.getenv("DEVIN_ORG_ID")
        self.base_url = "https://api.devin.ai/v3"
        
        if not all([self.api_key, self.org_id]):
            raise ValueError("DEVIN_API_KEY and DEVIN_ORG_ID must be set")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get common headers for API requests"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def _api_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make API request with error handling"""
        url = f"{self.base_url}{endpoint}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.request(method, url, headers=self._get_headers(), **kwargs)
                response.raise_for_status()
                body = response.json()
                logger.info("Devin API %s %s response: %s", method, endpoint, json.dumps(body, indent=2))
                return body
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                error_body = e.response.text
                logger.error("Devin API %s %s failed with %s: %s", method, endpoint, status, error_body)
                if status == 401:
                    raise Exception("Invalid or expired Devin API key")
                elif status == 403:
                    raise Exception("Insufficient permissions for this operation")
                elif status == 404:
                    raise Exception("Resource not found")
                elif status == 429:
                    raise Exception("Rate limit exceeded - wait and retry")
                else:
                    raise Exception(f"Devin API error {status}: {error_body}")
            except httpx.TimeoutException:
                raise Exception("Request to Devin API timed out")
            except httpx.RequestError as e:
                raise Exception(f"Network error: {str(e)}")
    
    async def create_session(
        self, 
        prompt: str, 
        repository: Optional[str] = None,
        issue_number: Optional[int] = None,
        automation_type: str = "general",
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a new Devin session"""
        # Enhance prompt with context
        enhanced_prompt = prompt
        if repository:
            enhanced_prompt = f"Repository: {repository}\n\n{prompt}"
        if issue_number:
            enhanced_prompt = f"Issue #{issue_number}\n\n{enhanced_prompt}"
        
        # Add automation-specific context
        if automation_type == "dependency_upgrade":
            enhanced_prompt = f"""
Task: Dependency Upgrade
{enhanced_prompt}

Please:
1. Identify outdated dependencies
2. Update them to latest compatible versions
3. Run tests to ensure compatibility
4. Create a pull request with your changes
5. Include changelog and breaking changes in PR description
"""
        elif automation_type == "vulnerability_fix":
            enhanced_prompt = f"""
Task: Security Vulnerability Fix
{enhanced_prompt}

Please:
1. Identify security vulnerabilities
2. Apply appropriate patches
3. Verify the fix resolves the vulnerability
4. Create a pull request with security details
5. Include CVE references and impact assessment
"""
        
        payload = {
            "prompt": enhanced_prompt,
            "tags": tags or [automation_type, "automated"],
            "resumable": False,  # Don't auto-resume suspended sessions
            "max_acu_limit": 100  # Limit ACU consumption per session
        }
        
        if repository:
            payload["repos"] = [repository]
        
        try:
            result = await self._api_request(
                "POST",
                f"/organizations/{self.org_id}/sessions",
                json=payload
            )
            logger.info(f"Created Devin session: {result.get('session_id')}")
            return result
        except Exception as e:
            logger.error(f"Failed to create Devin session: {e}")
            raise
    
    async def get_session(self, session_id: str) -> Dict[str, Any]:
        """Get session details"""
        try:
            result = await self._api_request(
                "GET",
                f"/organizations/{self.org_id}/sessions/{session_id}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            raise
    
    async def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Get session messages/events"""
        try:
            result = await self._api_request(
                "GET",
                f"/organizations/{self.org_id}/sessions/{session_id}/messages"
            )
            return result.get("items", [])
        except Exception as e:
            logger.error(f"Failed to get session messages for {session_id}: {e}")
            raise

    async def terminate_session(self, session_id: str, archive: bool = False) -> Dict[str, Any]:
        """Terminate a session"""
        try:
            result = await self._api_request(
                "DELETE",
                f"/organizations/{self.org_id}/sessions/{session_id}",
                params={"archive": archive}
            )
            logger.info(f"Terminated Devin session: {session_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to terminate session {session_id}: {e}")
            raise
    
    async def wait_for_completion(
        self,
        session_id: str,
        timeout: int = 3600,
        poll_interval: int = 5
    ) -> Dict[str, Any]:
        """Wait for session completion with polling"""
        start_time = datetime.utcnow()
        
        while True:
            # Check timeout
            if (datetime.utcnow() - start_time).total_seconds() > timeout:
                raise TimeoutError(f"Session {session_id} did not complete within {timeout} seconds")
            
            try:
                session = await self.get_session(session_id)
                status = session.get("status")
                
                logger.info(f"Session {session_id} status: {status}")
                
                # Check if session is complete
                if status in ["exit", "error"]:
                    return session
                
                # Wait before next poll
                await asyncio.sleep(poll_interval)
                
            except Exception as e:
                logger.error(f"Error polling session {session_id}: {e}")
                raise
    
    async def list_sessions(
        self, 
        limit: int = 50,
        status_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List sessions with optional filtering"""
        try:
            params = {"first": limit}
            if status_filter:
                params["status"] = status_filter
            
            result = await self._api_request(
                "GET",
                f"/organizations/{self.org_id}/sessions",
                params=params
            )
            
            sessions = result.get("items", [])
            logger.info(f"Retrieved {len(sessions)} sessions")
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            raise
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get queue status for the organization"""
        try:
            result = await self._api_request("GET", "/enterprise/queue")
            logger.info(f"Queue status: {result.get('queue_size')} sessions, status: {result.get('status')}")
            return result
        except Exception as e:
            logger.error(f"Failed to get queue status: {e}")
            raise
    
    def parse_session_result(self, session: Dict[str, Any]) -> Dict[str, Any]:
        """Parse session result for database storage"""
        return {
            "session_id": session.get("session_id"),
            "status": session.get("status"),
            "status_detail": session.get("status_detail"),
            "acus_consumed": session.get("acus_consumed", 0.0),
            "pull_requests": json.dumps(session.get("pull_requests", [])),
            "structured_output": json.dumps(session.get("structured_output", {})),
            "session_url": session.get("url"),
            "tags": session.get("tags", []),
            "title": session.get("title")
        }
    
    def is_session_successful(self, session: Dict[str, Any]) -> bool:
        """Determine if session completed successfully"""
        status = session.get("status")
        if status == "exit":
            # Check for structured output indicating success
            structured_output = session.get("structured_output", {})
            if isinstance(structured_output, dict):
                return structured_output.get("result") == "success"
            return True  # Assume exit means success
        return False
    
    def get_pull_requests_from_session(self, session: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract pull requests from session result"""
        return session.get("pull_requests", [])
