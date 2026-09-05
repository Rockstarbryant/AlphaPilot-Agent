"use client";

import { Panel } from "@/components/ui";

export default function EarnPage() {
  return (
    <Panel title="Simple Earn">
      <div className="px-4 py-6 text-sm text-muted max-w-lg">
        Binance Simple Earn is not part of Agent OS&apos;s documented scope as of the last
        capability-matrix research pass (see docs/BINANCE_CAPABILITY_MATRIX.md). AlphaPilot will
        recommend an idle-capital allocation via the Capital Optimizer (see Settings), but will
        never subscribe or redeem Earn products automatically — that action stays manual until
        Binance publishes a verified path for it.
      </div>
    </Panel>
  );
}
