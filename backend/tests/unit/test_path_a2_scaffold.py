import pytest

from app.binance.agent_os_mcp_client import BinanceAgentOSClient, BinanceMCPError, BinanceTool


def test_direct_agent_os_client_exists():
    client = BinanceAgentOSClient()
    assert client.endpoint == "https://agent.binance.com/mcp/agentic"


def test_tool_arguments_follow_live_schema():
    tool = BinanceTool(
        name="place_order",
        description="Place an order",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "type": {"type": "string"},
                "quoteOrderQty": {"type": "string"},
            },
            "required": ["symbol", "side", "type", "quoteOrderQty"],
        },
    )
    args = client_args = BinanceAgentOSClient._arguments_for(
        tool,
        symbol="BTCUSDT",
        side="BUY",
        type="MARKET",
        quantity=0.01,
        quote_amount=25.0,
    )
    assert args == {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "MARKET",
        "quoteOrderQty": "25.0",
    }


def test_tool_arguments_fail_closed_when_required_field_missing():
    tool = BinanceTool(
        name="place_order",
        description=None,
        input_schema={"properties": {"symbol": {}}, "required": ["symbol", "side"]},
    )
    with pytest.raises(BinanceMCPError):
        BinanceAgentOSClient._arguments_for(tool, symbol="BTCUSDT")
