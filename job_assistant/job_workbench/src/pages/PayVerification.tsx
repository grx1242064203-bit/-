import { useEffect, useRef, useState } from "react";
import { open as openShell } from "@tauri-apps/plugin-shell";
import { paymentsApi, PRODUCTS, type OrderStatusResponse, type EntitlementResponse } from "../api/payments";

const POLL_INTERVAL_MS = 2000;

function formatPrice(cents: number): string {
  return `¥${(cents / 100).toFixed(2)}`;
}

export default function PayVerification() {
  const [entitlement, setEntitlement] = useState<EntitlementResponse | null>(null);
  const [entError, setEntError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [orderId, setOrderId] = useState<string | null>(null);
  const [orderStatus, setOrderStatus] = useState<OrderStatusResponse | null>(null);
  const [payUrl, setPayUrl] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollTimer = useRef<number | null>(null);

  const addLog = (msg: string) => {
    const ts = new Date().toLocaleTimeString();
    setLog((l) => [...l, `[${ts}] ${msg}`]);
  };

  const loadEntitlement = async () => {
    try {
      const e = await paymentsApi.getEntitlement();
      setEntitlement(e);
      setEntError(null);
    } catch (e) {
      const err = e as { error?: string };
      setEntError(err?.error || "权益查询失败");
    }
  };

  useEffect(() => {
    void loadEntitlement();
    return () => {
      if (pollTimer.current) window.clearInterval(pollTimer.current);
    };
  }, []);

  const stopPolling = () => {
    if (pollTimer.current) {
      window.clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  };

  const startPolling = (id: string) => {
    stopPolling();
    addLog(`开始轮询订单状态（每 ${POLL_INTERVAL_MS}ms）`);
    pollTimer.current = window.setInterval(async () => {
      try {
        const s = await paymentsApi.getOrderStatus(id);
        setOrderStatus(s);
        if (s.status === "delivered" || s.status === "paid") {
          addLog(`订单状态变为 ${s.status}，停止轮询 + 刷新权益`);
          stopPolling();
          await loadEntitlement();
        }
      } catch (e) {
        const err = e as { error?: string };
        addLog(`轮询失败：${err?.error || "unknown"}`);
      }
    }, POLL_INTERVAL_MS);
  };

  const handleCreateOrder = async (productCode: string) => {
    setBusy(true);
    setError(null);
    setLog([]);
    setOrderStatus(null);
    setPayUrl(null);
    try {
      addLog(`创建订单：product_code=${productCode}`);
      const res = await paymentsApi.createOrder(productCode);
      setOrderId(res.order_id);
      setPayUrl(res.pay_url);
      addLog(`订单已创建：order_id=${res.order_id}，金额=${formatPrice(res.amount_cents)}`);
      addLog(`pay_url=${res.pay_url}`);
      startPolling(res.order_id);
    } catch (e) {
      const err = e as { error?: string; status?: number };
      setError(err?.error || "订单创建失败");
    } finally {
      setBusy(false);
    }
  };

  const handleOpenPayUrl = async () => {
    if (!payUrl) return;
    try {
      addLog(`通过 shell.open 在系统浏览器打开支付页`);
      await openShell(payUrl);
      addLog(`系统浏览器已打开（用户在此完成支付）`);
    } catch (e) {
      const err = e as { error?: string };
      addLog(`shell.open 失败：${err?.error || "unknown"}`);
    }
  };

  const handleSimulateNotify = async () => {
    if (!orderId) return;
    try {
      addLog(`模拟支付宝异步通知服务端（真实接入时由支付宝 POST /payments/notify）`);
      const res = await paymentsApi.simulateNotify(orderId);
      addLog(`服务端响应：${res.msg}，订单状态=${res.status}`);
    } catch (e) {
      const err = e as { error?: string };
      addLog(`模拟通知失败：${err?.error || "unknown"}`);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-line bg-surface p-5">
        <h2 className="text-lg font-semibold text-text">卡点1 验证：Tauri 支付回跳架构</h2>
        <p className="mt-1 text-sm text-text-muted">
          本页验证「系统浏览器 + 服务端轮询」架构能否绕过 Tauri webview 回跳依赖。
          真相源是服务端订单状态（由支付宝异步 notify 写入），与 webview 行为无关。
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-2xl border border-line bg-surface p-5">
          <div className="text-xs text-text-muted">当前权益</div>
          {entError ? (
            <div className="mt-2 text-sm text-warning">{entError}</div>
          ) : entitlement ? (
            <div className="mt-2 space-y-1">
              <div className="text-base font-semibold text-text">
                {entitlement.type ? (entitlement.type === "lifetime" ? "永久买断" : "月度试用") : "未购买"}
              </div>
              <div className="text-xs text-text-muted">
                active={String(entitlement.active)}
                {entitlement.expires_at ? ` · 到期 ${entitlement.expires_at}` : ""}
              </div>
              <button
                type="button"
                onClick={() => void loadEntitlement()}
                className="mt-2 rounded-pill bg-primary px-3 py-1 text-xs text-ink"
              >
                刷新
              </button>
            </div>
          ) : (
            <div className="mt-2 text-sm text-text-muted">加载中…</div>
          )}
        </div>

        <div className="rounded-2xl border border-line bg-surface p-5">
          <div className="text-xs text-text-muted">订单状态</div>
          {orderStatus ? (
            <div className="mt-2 space-y-1">
              <div className="text-base font-semibold text-text">
                {orderStatus.status}
              </div>
              <div className="text-xs text-text-muted">
                {formatPrice(orderStatus.amount_cents)} · {orderStatus.product_code}
              </div>
              {orderStatus.delivered_at && (
                <div className="text-xs text-text-muted">
                  delivered_at={orderStatus.delivered_at}
                </div>
              )}
            </div>
          ) : (
            <div className="mt-2 text-sm text-text-muted">无</div>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-line bg-surface p-5">
        <div className="mb-3 text-sm font-medium text-text">商品</div>
        <div className="grid gap-3 sm:grid-cols-2">
          {PRODUCTS.map((p) => (
            <div
              key={p.code}
              className="rounded-xl border border-line bg-surface-muted p-4"
            >
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium text-text">{p.name}</div>
                <div className="text-sm text-text">{formatPrice(p.price_cents)}</div>
              </div>
              <div className="mt-1 text-xs text-text-muted">
                {p.lifetime ? "永久" : `${p.duration_days} 天`}
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={() => void handleCreateOrder(p.code)}
                className="mt-3 w-full rounded-pill bg-ink px-3 py-1.5 text-xs text-white disabled:opacity-50"
              >
                创建订单
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-line bg-surface p-5">
        <div className="mb-3 text-sm font-medium text-text">支付验证步骤</div>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            disabled={!payUrl}
            onClick={() => void handleOpenPayUrl()}
            className="rounded-pill bg-primary px-4 py-2 text-xs text-ink disabled:opacity-50"
          >
            ① 在系统浏览器打开支付页
          </button>
          <button
            type="button"
            disabled={!orderId}
            onClick={() => void handleSimulateNotify()}
            className="rounded-pill bg-primary px-4 py-2 text-xs text-ink disabled:opacity-50"
          >
            ② 模拟支付宝异步通知
          </button>
        </div>
        {error && <div className="mt-2 text-xs text-warning">{error}</div>}
      </div>

      <div className="rounded-2xl border border-line bg-surface p-5">
        <div className="mb-3 text-sm font-medium text-text">验证日志</div>
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-xl bg-surface-muted p-3 text-xs text-text-muted">
          {log.length ? log.join("\n") : "暂无日志"}
        </pre>
      </div>
    </div>
  );
}
