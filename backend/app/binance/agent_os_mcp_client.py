"""Direct Binance Agent OS MCP client.

This module is deliberately provider-oriented: AlphaPilot is an MCP *client*
to Binance Agent OS, not merely an MCP server for another AI client.

Authentication is delegated to the standard MCP OAuth authorization flow.
No Binance API key, Binance password, or Binance-specific OAuth credential is
stored by AlphaPilot. The MCP access/refresh tokens returned by the protected
MCP authorization server are encrypted at rest so the backend can reconnect
after the browser authorization step.

The Binance endpoint is discovered at runtime and its tool catalog is inspected
before calls are made. We do not assume that an arbitrary third-party Binance
MCP implementation is the same as Binance's hosted Agent OS MCP.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

settings = get_settings()
MCP_ENDPOINT = settings.binance_mcp_endpoint


class BinanceMCPError(RuntimeError):
    pass


class BinanceMCPAuthenticationError(BinanceMCPError):
    pass


class BinanceMCPToolError(BinanceMCPError):
    pass


@dataclass
class BinanceTool:
    name: str
    description: str | None
    input_schema: dict[str, Any]


@dataclass
class MCPOAuthDiscovery:
    resource_metadata_url: str
    authorization_servers: list[str]
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str | None
    scopes_supported: list[str]


@dataclass
class BinanceConnectionData:
    access_token: str
    refresh_token: str | None = None
    expires_at: int | None = None

    @property
    def expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= int(time.time()) + 30


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _pkce_verifier() -> str:
    return _b64url(secrets.token_bytes(32))


def _pkce_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode()).digest())


def encrypt_secret(value: str) -> str:
    key = settings.mcp_oauth_encryption_key
    if not key:
        raise BinanceMCPAuthenticationError(
            "MCP_OAUTH_ENCRYPTION_KEY is required before storing protected-MCP tokens."
        )
    try:
        return Fernet(key.encode()).encrypt(value.encode()).decode()
    except Exception as exc:
        raise BinanceMCPAuthenticationError("Invalid MCP_OAUTH_ENCRYPTION_KEY.") from exc


def decrypt_secret(value: str) -> str:
    key = settings.mcp_oauth_encryption_key
    if not key:
        raise BinanceMCPAuthenticationError("MCP_OAUTH_ENCRYPTION_KEY is not configured.")
    try:
        return Fernet(key.encode()).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise BinanceMCPAuthenticationError("Stored MCP authorization credential could not be decrypted.") from exc


class MCPOAuthManager:
    """Generic MCP OAuth discovery/authorization helpers.

    This class intentionally knows nothing about Binance Login/OAuth. It only
    implements the protected-MCP authorization contract: resource metadata,
    authorization-server discovery, dynamic client registration when advertised,
    PKCE, and token exchange. Binance owns the authorization UI and scopes.
    """

    def __init__(self, endpoint: str = MCP_ENDPOINT):
        self.endpoint = endpoint
        self.timeout = httpx.Timeout(20.0, connect=10.0)

    async def discover(self) -> MCPOAuthDiscovery:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.post(
                self.endpoint,
                headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "alphapilot", "version": "0.2.0"},
                    },
                },
            )
            if response.status_code != 401:
                # A future/alternate Binance configuration may permit public discovery.
                if response.status_code >= 400:
                    raise BinanceMCPAuthenticationError(
                        f"Binance MCP discovery failed with HTTP {response.status_code}."
                    )
                raise BinanceMCPAuthenticationError(
                    "Binance MCP did not return the expected OAuth challenge."
                )

            challenge = response.headers.get("WWW-Authenticate", "")
            resource_url = self._resource_metadata_from_challenge(challenge)
            if not resource_url:
                resource_url = urljoin(self.endpoint, "/.well-known/oauth-protected-resource/gateway-mcp")

            meta = await client.get(resource_url)
            meta.raise_for_status()
            resource = meta.json()
            servers = resource.get("authorization_servers") or []
            if not servers:
                raise BinanceMCPAuthenticationError("MCP protected-resource metadata did not advertise an authorization server.")

            issuer = servers[0].rstrip("/")
            parsed = urlparse(issuer)
            as_meta_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/.well-known/oauth-authorization-server"
            as_response = await client.get(as_meta_url)
            as_response.raise_for_status()
            auth = as_response.json()

            authorization_endpoint = auth.get("authorization_endpoint")
            token_endpoint = auth.get("token_endpoint")
            if not authorization_endpoint or not token_endpoint:
                raise BinanceMCPAuthenticationError("MCP authorization-server metadata is missing required endpoints.")

            return MCPOAuthDiscovery(
                resource_metadata_url=resource_url,
                authorization_servers=servers,
                authorization_endpoint=authorization_endpoint,
                token_endpoint=token_endpoint,
                registration_endpoint=auth.get("registration_endpoint"),
                scopes_supported=resource.get("scopes_supported") or auth.get("scopes_supported") or [],
            )

    @staticmethod
    def _resource_metadata_from_challenge(challenge: str) -> str | None:
        marker = "resource_metadata="
        if marker not in challenge:
            return None
        raw = challenge.split(marker, 1)[1].split(",", 1)[0].strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        return raw or None

    async def begin(self, *, user_id: str, redirect_uri: str) -> dict[str, str | None]:
        discovery = await self.discover()
        if not discovery.registration_endpoint:
            raise BinanceMCPAuthenticationError(
                "MCP authorization server did not advertise dynamic client registration."
            )

        metadata = {
            "client_name": settings.mcp_client_name,
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            registration = await client.post(discovery.registration_endpoint, json=metadata)
            registration.raise_for_status()
            client_info = registration.json()

        client_id = client_info.get("client_id")
        if not client_id:
            raise BinanceMCPAuthenticationError("MCP dynamic registration returned no client_id.")

        verifier = _pkce_verifier()
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
            "state": secrets.token_urlsafe(32),
            "resource": self.endpoint,
        }
        authorization_url = f"{discovery.authorization_endpoint}?{urlencode(params)}"
        return {
            "authorization_url": authorization_url,
            "state": params["state"],
            "code_verifier": verifier,
            "client_id": client_id,
            "token_endpoint": discovery.token_endpoint,
            "resource_metadata_url": discovery.resource_metadata_url,
            "user_id": user_id,
        }

    async def exchange_code(
        self,
        *,
        code: str,
        state: str,
        expected_state: str,
        code_verifier: str,
        redirect_uri: str,
        client_id: str,
        token_endpoint: str,
    ) -> dict[str, Any]:
        if not secrets.compare_digest(state, expected_state):
            raise BinanceMCPAuthenticationError("MCP OAuth state mismatch.")
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
            "resource": self.endpoint,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(token_endpoint, data=payload)
            if response.status_code >= 400:
                raise BinanceMCPAuthenticationError(
                    f"MCP OAuth token exchange failed ({response.status_code}): {response.text[:500]}"
                )
            return response.json()

    async def refresh(self, *, refresh_token: str, client_id: str, token_endpoint: str) -> dict[str, Any]:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "resource": self.endpoint,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(token_endpoint, data=payload)
            if response.status_code >= 400:
                raise BinanceMCPAuthenticationError(
                    f"MCP OAuth refresh failed ({response.status_code}): {response.text[:500]}"
                )
            return response.json()


class BinanceAgentOSClient:
    """Small, explicit Streamable HTTP MCP client used by AlphaPilot core."""

    def __init__(self, connection: BinanceConnectionData | None = None, endpoint: str = MCP_ENDPOINT):
        self.endpoint = endpoint
        self.connection = connection
        self.session_id: str | None = None
        self._request_id = 0
        self._tools: dict[str, BinanceTool] | None = None

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self.connection and self.connection.access_token:
            headers["Authorization"] = f"Bearer {self.connection.access_token}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._request_id += 1
        body = {"jsonrpc": "2.0", "id": self._request_id, "method": method}
        if params is not None:
            body["params"] = params
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True) as client:
            response = await client.post(self.endpoint, headers=self._headers(), json=body)
            if response.status_code == 401:
                raise BinanceMCPAuthenticationError("Binance Agent OS authorization is missing or expired.")
            if response.status_code >= 400:
                raise BinanceMCPError(f"Binance MCP HTTP {response.status_code}: {response.text[:500]}")
            sid = response.headers.get("Mcp-Session-Id")
            if sid:
                self.session_id = sid
            return self._decode_response(response)

    @staticmethod
    def _decode_response(response: httpx.Response) -> Any:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type or not content_type:
            payload = response.json()
            if "error" in payload:
                raise BinanceMCPError(payload["error"].get("message", str(payload["error"])))
            return payload.get("result")

        # Streamable HTTP may return SSE. Collect the JSON-RPC data event(s).
        events: list[Any] = []
        for line in response.text.splitlines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        if not events:
            raise BinanceMCPError("Binance MCP returned an empty/unsupported response.")
        payload = events[-1]
        if "error" in payload:
            raise BinanceMCPError(payload["error"].get("message", str(payload["error"])))
        return payload.get("result")

    async def initialize(self) -> dict[str, Any]:
        result = await self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "alphapilot", "version": "0.2.0"},
            },
        )
        return result or {}

    async def list_tools(self, *, refresh: bool = False) -> list[BinanceTool]:
        if self._tools is not None and not refresh:
            return list(self._tools.values())
        result = await self._rpc("tools/list", {})
        tools = {}
        for raw in (result or {}).get("tools", []):
            tool = BinanceTool(
                name=raw["name"],
                description=raw.get("description"),
                input_schema=raw.get("inputSchema") or {},
            )
            tools[tool.name] = tool
        self._tools = tools
        return list(tools.values())

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        if isinstance(result, dict) and result.get("isError"):
            content = result.get("content") or []
            raise BinanceMCPToolError(json.dumps(content)[:1000])
        return result

    async def get_ticker(self, symbol: str) -> Any:
        await self._ensure_initialized()
        tool = self._resolve_tool("get_ticker", "ticker", "price")
        return await self.call_tool(tool.name, self._arguments_for(tool, symbol=symbol))

    async def get_account_state(self) -> Any:
        await self._ensure_initialized()
        tool = self._resolve_tool("get_balance", "get_portfolio", "get_account", "account_balance", "balance")
        return await self.call_tool(tool.name, {})

    async def place_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        quote_amount: float | None = None,
        price: float | None = None,
        leverage: float | None = None,
    ) -> Any:
        await self._ensure_initialized()
        tool = self._resolve_tool("place_order", "create_order", "submit_order")
        args = self._arguments_for(
            tool,
            symbol=symbol,
            side=side,
            type=order_type,
            order_type=order_type,
            quantity=str(quantity),
            quoteOrderQty=str(quote_amount) if quote_amount is not None else None,
            quote_amount=str(quote_amount) if quote_amount is not None else None,
            price=str(price) if price is not None else None,
            leverage=leverage,
        )
        return await self.call_tool(tool.name, args)

    async def get_order_status(self, *, symbol: str, order_id: str) -> Any:
        await self._ensure_initialized()
        tool = self._resolve_tool("get_order_status", "fetch_order_status", "order_info", "get_order")
        return await self.call_tool(tool.name, self._arguments_for(tool, symbol=symbol, orderId=order_id, order_id=order_id))

    async def cancel_order(self, *, symbol: str, order_id: str) -> Any:
        await self._ensure_initialized()
        tool = self._resolve_tool("cancel_order", "remove_order", "revoke_order")
        return await self.call_tool(tool.name, self._arguments_for(tool, symbol=symbol, orderId=order_id, order_id=order_id))

    async def _ensure_initialized(self) -> None:
        if self._tools is None:
            await self.initialize()
            await self.list_tools()

    def _resolve_tool(self, *preferred: str) -> BinanceTool:
        if not self._tools:
            raise BinanceMCPError("Binance MCP tool catalog is empty. Initialize and list tools first.")
        for name in preferred:
            if name in self._tools:
                return self._tools[name]
        lowered = {k.lower(): v for k, v in self._tools.items()}
        for name in preferred:
            for key, tool in lowered.items():
                if name.lower() in key:
                    return tool
        raise BinanceMCPToolError(
            f"Required Binance capability not exposed by the connected Agent OS server. Available: {sorted(self._tools)}"
        )

    @staticmethod
    def _arguments_for(tool: BinanceTool, **values: Any) -> dict[str, Any]:
        properties = tool.input_schema.get("properties") or {}
        required = tool.input_schema.get("required") or []
        result: dict[str, Any] = {}
        aliases = {
            "type": ["order_type", "type"],
            "order_type": ["type", "order_type"],
            "orderId": ["orderId", "order_id", "id"],
            "order_id": ["order_id", "orderId", "id"],
            "quoteOrderQty": ["quoteOrderQty", "quote_order_qty", "quote_amount"],
            "quote_amount": ["quote_amount", "quoteOrderQty", "quote_order_qty"],
        }
        for key, value in values.items():
            if value is None:
                continue
            candidates = aliases.get(key, [key])
            chosen = next((candidate for candidate in candidates if candidate in properties), None)
            if chosen:
                result[chosen] = value
        missing = [key for key in required if key not in result]
        if missing:
            raise BinanceMCPToolError(
                f"Cannot safely call Binance tool '{tool.name}': required arguments unavailable: {missing}."
            )
        return result


async def connect_self_built_agent(*args: Any, **kwargs: Any) -> BinanceAgentOSClient:
    """Backward-compatible entry point: returns the real direct MCP client."""
    return BinanceAgentOSClient()
