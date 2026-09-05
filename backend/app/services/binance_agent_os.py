"""AlphaPilot <-> Binance Agent OS orchestration.

This is the boundary between AlphaPilot's strategy/risk layers and Binance's
hosted MCP server. It owns the protected-MCP connection state and translates
AlphaPilot TradePlans into Binance Agent OS MCP tool calls. Authentication is
standard MCP OAuth; Binance controls the authorization UI and scopes.
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.binance.agent_os_mcp_client import (
    BinanceAgentOSClient,
    BinanceConnectionData,
    BinanceMCPAuthenticationError,
    MCPOAuthManager,
    decrypt_secret,
    encrypt_secret,
)
from app.core.config import get_settings
from app.models.models import AuditEvent, BinanceConnection, BinanceConnectionStatus, ExitSignal, Position, PositionStatus, TradePlan, TradePlanStatus

settings = get_settings()


class BinanceAgentOSService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.oauth = MCPOAuthManager()

    async def connection(self, user_id: str) -> BinanceConnection | None:
        result = await self.db.execute(
            select(BinanceConnection).where(BinanceConnection.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def begin_authorization(self, user_id: str) -> dict[str, Any]:
        redirect_uri = settings.mcp_oauth_redirect_uri
        flow = await self.oauth.begin(user_id=user_id, redirect_uri=redirect_uri)
        connection = await self.connection(user_id)
        if connection is None:
            connection = BinanceConnection(user_id=user_id)
            self.db.add(connection)
        connection.status = BinanceConnectionStatus.pending
        connection.client_id = str(flow["client_id"])
        connection.token_endpoint = str(flow["token_endpoint"])
        connection.oauth_state = str(flow["state"])
        connection.code_verifier_encrypted = encrypt_secret(str(flow["code_verifier"]))
        connection.redirect_uri = redirect_uri
        connection.last_error = None
        await self.db.commit()
        return {"authorization_url": flow["authorization_url"]}

    async def complete_authorization(self, *, code: str, state: str) -> BinanceConnection:
        result = await self.db.execute(
            select(BinanceConnection).where(BinanceConnection.oauth_state == state)
        )
        connection = result.scalar_one_or_none()
        if connection is None or not connection.client_id or not connection.token_endpoint:
            raise BinanceMCPAuthenticationError("Unknown or expired MCP authorization state.")
        if not connection.code_verifier_encrypted:
            raise BinanceMCPAuthenticationError("MCP authorization PKCE verifier is missing.")

        try:
            token = await self.oauth.exchange_code(
                code=code,
                state=state,
                expected_state=connection.oauth_state,
                code_verifier=decrypt_secret(connection.code_verifier_encrypted),
                redirect_uri=connection.redirect_uri or settings.mcp_oauth_redirect_uri,
                client_id=connection.client_id,
                token_endpoint=connection.token_endpoint,
            )
            access = token.get("access_token")
            if not access:
                raise BinanceMCPAuthenticationError("MCP OAuth response contained no access_token.")
            refresh = token.get("refresh_token")
            connection.access_token_encrypted = encrypt_secret(access)
            connection.refresh_token_encrypted = encrypt_secret(refresh) if refresh else None
            connection.token_expires_at = int(time.time()) + int(token.get("expires_in", 3600)) if token.get("expires_in") else None
            connection.oauth_state = None
            connection.code_verifier_encrypted = None
            connection.status = BinanceConnectionStatus.connected
            connection.connected_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            connection.last_error = None
            await self.db.commit()
            await self.db.refresh(connection)
            return connection
        except Exception as exc:
            connection.status = BinanceConnectionStatus.error
            connection.last_error = str(exc)[:1000]
            await self.db.commit()
            raise

    async def _access_token(self, connection: BinanceConnection) -> str:
        if not connection.access_token_encrypted:
            raise BinanceMCPAuthenticationError("Binance Agent OS is not authorized for this user.")
        if connection.token_expires_at and connection.token_expires_at <= int(time.time()) + 60:
            if not connection.refresh_token_encrypted or not connection.client_id or not connection.token_endpoint:
                raise BinanceMCPAuthenticationError("Binance authorization expired; reconnect the Agent OS account.")
            token = await self.oauth.refresh(
                refresh_token=decrypt_secret(connection.refresh_token_encrypted),
                client_id=connection.client_id,
                token_endpoint=connection.token_endpoint,
            )
            access = token.get("access_token")
            if not access:
                raise BinanceMCPAuthenticationError("Binance refresh response contained no access_token.")
            connection.access_token_encrypted = encrypt_secret(access)
            if token.get("refresh_token"):
                connection.refresh_token_encrypted = encrypt_secret(token["refresh_token"])
            connection.token_expires_at = int(time.time()) + int(token.get("expires_in", 3600)) if token.get("expires_in") else None
            await self.db.commit()
        return decrypt_secret(connection.access_token_encrypted)

    async def client(self, user_id: str) -> BinanceAgentOSClient:
        connection = await self.connection(user_id)
        if connection is None or connection.status != BinanceConnectionStatus.connected:
            raise BinanceMCPAuthenticationError("Binance Agent OS is not connected. Authorize AlphaPilot first.")
        token = await self._access_token(connection)
        return BinanceAgentOSClient(BinanceConnectionData(access_token=token, expires_at=connection.token_expires_at))

    async def capabilities(self, user_id: str) -> list[dict[str, Any]]:
        client = await self.client(user_id)
        await client.initialize()
        tools = await client.list_tools(refresh=True)
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]

    async def market_ticker(self, user_id: str, symbol: str) -> Any:
        return await (await self.client(user_id)).get_ticker(symbol)

    async def account_state(self, user_id: str) -> Any:
        return await (await self.client(user_id)).get_account_state()

    async def sync_account_snapshot(self, user_id: str) -> dict[str, Any]:
        """Read Agentic account state and persist a conservative USDT snapshot.

        The response shape is intentionally discovered rather than assumed.
        Only an explicit USDT-like balance is used as portfolio value; unknown
        fields remain zero instead of being fabricated.
        """
        raw = await self.account_state(user_id)
        usdt = self._find_asset_balance(raw, {"USDT"})
        from app.models.models import AccountSnapshot
        snapshot = AccountSnapshot(
            user_id=user_id, portfolio_value_usdt=usdt, open_exposure_usdt=0.0,
            margin_exposure_usdt=0.0, realized_daily_loss_pct=0.0, source="agent_os_mcp",
        )
        self.db.add(snapshot)
        await self.db.commit()
        return {"portfolio_value_usdt": usdt, "raw": raw}

    @staticmethod
    def _find_asset_balance(value: Any, assets: set[str]) -> float:
        if isinstance(value, dict):
            asset = str(value.get("asset") or value.get("currency") or value.get("coin") or "").upper()
            if asset in assets:
                for key in ("free", "available", "availableBalance", "balance", "walletBalance", "equity", "total"):
                    try:
                        if value.get(key) is not None:
                            return float(value[key])
                    except (TypeError, ValueError):
                        pass
            for child in value.values():
                found = BinanceAgentOSService._find_asset_balance(child, assets)
                if found > 0:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = BinanceAgentOSService._find_asset_balance(child, assets)
                if found > 0:
                    return found
        return 0.0

    async def execute_trade_plan(self, plan: TradePlan) -> dict[str, Any]:
        if not plan.risk_check_passed:
            raise ValueError("Risk-rejected TradePlan cannot be executed.")
        if plan.status not in (TradePlanStatus.proposed, TradePlanStatus.approved):
            raise ValueError(f"TradePlan is '{plan.status.value}' and is not executable.")

        client = await self.client(plan.user_id)
        quantity = plan.position_size_usdt / plan.entry_price if plan.entry_price else 0.0
        plan.status = TradePlanStatus.submitting
        await self.db.commit()

        try:
            result = await client.place_order(
                symbol=plan.symbol,
                side=plan.side,
                order_type="MARKET",
                quantity=quantity,
                quote_amount=plan.position_size_usdt if plan.side.upper() == "BUY" else None,
            )
            order_id = self.extract_order_id(result)
            if not order_id:
                # Binance may return a confirmation/pending object rather than a fill.
                plan.status = TradePlanStatus.approved
                await self.db.commit()
                return {"status": "confirmation_required", "result": result}

            status_result = await client.get_order_status(symbol=plan.symbol, order_id=order_id)
            status = self.normalize_order_status(status_result)
            if status in {"FILLED", "PARTIALLY_FILLED"}:
                plan.binance_order_id = order_id
                plan.executed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                if status == "FILLED":
                    plan.status = TradePlanStatus.open
                    position = await self._create_position_from_fill(plan, status_result)
                    await self.db.commit()
                    return {"status": "filled", "order_id": order_id, "position_id": position.id, "order": status_result}
                plan.status = TradePlanStatus.submitting
                await self.db.commit()
                return {"status": "partially_filled", "order_id": order_id, "order": status_result}

            plan.binance_order_id = order_id
            plan.status = TradePlanStatus.submitting
            await self.db.commit()
            return {"status": "submitted", "order_id": order_id, "order": status_result}
        except Exception:
            plan.status = TradePlanStatus.failed
            await self.db.commit()
            raise

    async def _create_position_from_fill(self, plan: TradePlan, order_result: Any) -> Position:
        existing = (await self.db.execute(select(Position).where(Position.trade_plan_id == plan.id))).scalar_one_or_none()
        if existing is not None:
            return existing
        fill_price = self._extract_float(order_result, "avgPrice", "averagePrice", "fill_price") or plan.entry_price
        quantity = self._extract_float(order_result, "executedQty", "filled_quantity", "quantity")
        if not quantity:
            quantity = plan.position_size_usdt / fill_price if fill_price else 0.0
        position = Position(
            trade_plan_id=plan.id, user_id=plan.user_id, symbol=plan.symbol, strategy=plan.strategy,
            entry_price=fill_price, quantity=quantity, remaining_fraction=1.0,
            stop_loss_pct=plan.stop_loss_pct, profit_targets_pct=plan.profit_targets_pct,
            targets_hit={}, peak_price_since_entry=fill_price,
        )
        self.db.add(position)
        self.db.add(AuditEvent(
            user_id=plan.user_id, strategy=plan.strategy.value, action="position_opened_via_binance_agent_os",
            asset=plan.symbol, decision="OPEN", status="ok",
            risk_result={"binance_order_id": plan.binance_order_id, "fill_price": fill_price, "quantity": quantity},
        ))
        await self.db.flush()
        return position

    @staticmethod
    def _extract_float(result: Any, *keys: str) -> float | None:
        if isinstance(result, dict):
            for key in keys:
                if result.get(key) is not None:
                    try:
                        return float(result[key])
                    except (TypeError, ValueError):
                        pass
            for container in (result.get("data"), result.get("result"), result.get("structuredContent")):
                value = BinanceAgentOSService._extract_float(container, *keys)
                if value is not None:
                    return value
        return None

    async def execute_exit_signal(self, signal: ExitSignal) -> dict[str, Any]:
        position = await self.db.get(Position, signal.position_id)
        if position is None:
            raise ValueError("Position for exit signal no longer exists.")
        if signal.execution_status == "filled":
            return {"status": "already_filled", "order_id": signal.binance_order_id}
        if position.status == PositionStatus.closed:
            signal.execution_status = "filled"
            await self.db.commit()
            return {"status": "already_closed"}

        client = await self.client(position.user_id)
        quantity = max(0.0, position.quantity * min(signal.sell_fraction, position.remaining_fraction))
        if quantity <= 0:
            raise ValueError("Exit quantity is zero.")
        try:
            result = await client.place_order(
                symbol=position.symbol, side="SELL", order_type="MARKET", quantity=quantity
            )
            order_id = self.extract_order_id(result)
            if not order_id:
                signal.execution_status = "confirmation_required"
                await self.db.commit()
                return {"status": "confirmation_required", "result": result}
            signal.binance_order_id = order_id
            status_result = await client.get_order_status(symbol=position.symbol, order_id=order_id)
            status = self.normalize_order_status(status_result)
            if status == "FILLED":
                fraction = min(signal.sell_fraction, position.remaining_fraction)
                position.remaining_fraction = max(0.0, position.remaining_fraction - fraction)
                if signal.target_pct is not None:
                    position.targets_hit = {**position.targets_hit, str(signal.target_pct): True}
                if position.remaining_fraction <= 0.001:
                    position.remaining_fraction = 0.0
                    position.status = PositionStatus.closed
                    position.closed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                else:
                    position.status = PositionStatus.partially_exited
                signal.execution_status = "filled"
                signal.acknowledged = True
                await self.db.commit()
                return {"status": "filled", "order_id": order_id, "order": status_result}
            signal.execution_status = "submitted"
            await self.db.commit()
            return {"status": "submitted", "order_id": order_id, "order": status_result}
        except Exception:
            signal.execution_status = "failed"
            await self.db.commit()
            raise

    @staticmethod
    def extract_order_id(result: Any) -> str | None:
        if not isinstance(result, dict):
            return None
        for key in ("orderId", "order_id", "id"):
            if result.get(key) is not None:
                return str(result[key])
        for container in (result.get("data"), result.get("result"), result.get("structuredContent")):
            if isinstance(container, dict):
                found = BinanceAgentOSService.extract_order_id(container)
                if found:
                    return found
        return None

    @staticmethod
    def normalize_order_status(result: Any) -> str:
        if isinstance(result, dict):
            for key in ("status", "orderStatus"):
                if result.get(key):
                    return str(result[key]).upper()
            for container in (result.get("data"), result.get("result"), result.get("structuredContent")):
                status = BinanceAgentOSService.normalize_order_status(container)
                if status:
                    return status
        return ""
